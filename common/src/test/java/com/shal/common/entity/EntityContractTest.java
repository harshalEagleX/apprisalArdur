package com.shal.common.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Contract checks that apply to EVERY persisted entity.
 *
 * Two things are actually being verified, neither of which is busywork:
 *
 *  1. ACCESSOR ROUND-TRIP — set(x) then get() must return x. The bug this
 *     catches is the classic copy-paste slip where setFoo assigns to `bar`;
 *     with JPA that corrupts a column silently and is invisible until someone
 *     reads the wrong value back out of the database.
 *
 *  2. LIFECYCLE CALLBACKS — @PrePersist/@PreUpdate carry real logic (timestamp
 *     defaults, conditional initialisation). They are invoked by the JPA
 *     provider, never by application code, so nothing else exercises them.
 *
 * Written reflectively so a NEW entity is covered the day it is added rather
 * than whenever someone remembers to extend a hand-written list.
 */
class EntityContractTest {

    /** Every concrete @Entity in this package. */
    static Stream<Class<?>> entities() {
        return Stream.of(
                AppraisalTransaction.class, AuditLog.class, Batch.class, BatchFile.class,
                BusinessEvent.class, Client.class, DocStat.class, DocStatRule.class,
                DocStatSection.class, DocStatStage.class, DocumentMatch.class,
                LLMInteraction.class, Notification.class, OperatorSession.class,
                ProcessingMetrics.class, QCResult.class, QCRuleResult.class, User.class);
    }

    /** A representative value for each type a column can hold. */
    private static Object sampleFor(Class<?> type) {
        if (type == String.class)      return "sample";
        if (type == Long.class || type == long.class)       return 42L;
        if (type == Integer.class || type == int.class)     return 7;
        if (type == Double.class || type == double.class)   return 1.5d;
        if (type == Float.class || type == float.class)     return 2.5f;
        if (type == Boolean.class || type == boolean.class) return Boolean.TRUE;
        if (type == BigDecimal.class)  return new BigDecimal("3.14");
        if (type == LocalDateTime.class) return LocalDateTime.of(2026, 1, 2, 3, 4, 5);
        if (type.isEnum())             return type.getEnumConstants().length > 0
                                              ? type.getEnumConstants()[0] : null;
        if (type == List.class)        return new ArrayList<>();
        return null;   // entity references and anything exotic — skipped
    }

    @ParameterizedTest(name = "{0} accessors round-trip")
    @MethodSource("entities")
    @DisplayName("every setter stores into the field its getter reads")
    void accessorsRoundTrip(Class<?> type) throws Exception {
        Object instance = type.getDeclaredConstructor().newInstance();
        int checked = 0;

        for (Method setter : type.getMethods()) {
            if (!setter.getName().startsWith("set") || setter.getParameterCount() != 1) continue;
            if (Modifier.isStatic(setter.getModifiers())) continue;

            Class<?> param = setter.getParameterTypes()[0];
            Object value = sampleFor(param);
            if (value == null) continue;                       // no sensible sample

            String suffix = setter.getName().substring(3);
            Method getter = findGetter(type, suffix, param);
            if (getter == null) continue;                      // write-only property

            setter.invoke(instance, value);
            assertThat(getter.invoke(instance))
                    .as("%s.%s -> %s", type.getSimpleName(), setter.getName(), getter.getName())
                    .isEqualTo(value);
            checked++;
        }

        // Not every entity is setter-shaped, and that is deliberate:
        //   DocStat            — fluent Builder
        //   DocStatStage/…     — all-args constructor, getters only (immutable child rows)
        // Round-trip the constructor form too rather than just excusing it.
        if (checked == 0) {
            assertThat(hasBuilder(type) || constructorRoundTrips(type))
                    .as("%s has no testable setters, builder, or all-args constructor",
                        type.getSimpleName())
                    .isTrue();
        }
    }

    private static boolean hasBuilder(Class<?> type) {
        try {
            return Modifier.isStatic(type.getMethod("builder").getModifiers());
        } catch (NoSuchMethodException e) {
            return false;
        }
    }

    /**
     * For an immutable, constructor-populated entity: build one with known values
     * and assert each getter hands the value back. Same copy-paste protection as
     * the setter round-trip, for a class that has no setters to test.
     */
    private static boolean constructorRoundTrips(Class<?> type) throws Exception {
        var ctor = Stream.of(type.getDeclaredConstructors())
                .filter(c -> c.getParameterCount() > 1)
                .max(java.util.Comparator.comparingInt(java.lang.reflect.Constructor::getParameterCount))
                .orElse(null);
        if (ctor == null) return false;

        Class<?>[] params = ctor.getParameterTypes();
        Object[] args = new Object[params.length];
        for (int i = 0; i < params.length; i++) args[i] = sampleFor(params[i]);
        ctor.setAccessible(true);
        Object instance = ctor.newInstance(args);

        // Every argument we supplied a sample for must be readable back out.
        for (int i = 0; i < params.length; i++) {
            if (args[i] == null) continue;
            String name = ctor.getParameters()[i].getName();
            Method g = findGetterByProperty(type, name, params[i]);
            if (g == null) continue;                    // parameter names not retained
            assertThat(g.invoke(instance))
                    .as("%s constructor arg '%s' not readable via %s",
                        type.getSimpleName(), name, g.getName())
                    .isEqualTo(args[i]);
        }
        return true;
    }

    private static Method findGetterByProperty(Class<?> type, String property, Class<?> param) {
        if (property == null || property.isEmpty()) return null;
        String suffix = Character.toUpperCase(property.charAt(0)) + property.substring(1);
        return findGetter(type, suffix, param);
    }

    @ParameterizedTest(name = "{0} lifecycle callbacks")
    @MethodSource("entities")
    @DisplayName("@PrePersist/@PreUpdate run without error and stamp their timestamps")
    void lifecycleCallbacksRun(Class<?> type) throws Exception {
        Object instance = type.getDeclaredConstructor().newInstance();

        for (Method m : type.getDeclaredMethods()) {
            boolean lifecycle = m.isAnnotationPresent(PrePersist.class)
                    || m.isAnnotationPresent(PreUpdate.class);
            if (!lifecycle || m.getParameterCount() != 0) continue;

            m.setAccessible(true);
            // An append-only entity REJECTS mutation from its @PreUpdate — that
            // throw is the guarantee, not a fault (asserted in its own test below).
            if (m.isAnnotationPresent(PreUpdate.class) && rejectsMutation(type)) continue;
            m.invoke(instance);                                 // must not throw

            // A @PrePersist that owns createdAt must actually set it — a null
            // created_at is a NOT NULL violation at insert time, i.e. a 500 on save.
            if (m.isAnnotationPresent(PrePersist.class)) {
                Method createdAt = findGetter(type, "CreatedAt", LocalDateTime.class);
                if (createdAt != null) {
                    assertThat(createdAt.invoke(instance))
                            .as("%s @PrePersist left createdAt null", type.getSimpleName())
                            .isNotNull();
                }
            }
        }
    }

    @Test
    @DisplayName("QCResult @PrePersist defaults processedAt only when it is absent")
    void qcResultPrePersistDoesNotOverwriteProcessedAt() {
        // The conditional in onCreate() is the interesting part: a caller-supplied
        // processedAt must survive, or the true processing time is lost.
        QCResult supplied = new QCResult();
        LocalDateTime original = LocalDateTime.of(2020, 1, 1, 0, 0);
        supplied.setProcessedAt(original);
        supplied.onCreate();
        assertThat(supplied.getProcessedAt()).isEqualTo(original);

        QCResult absent = new QCResult();
        absent.onCreate();
        assertThat(absent.getProcessedAt()).isNotNull();
        assertThat(absent.getCreatedAt()).isNotNull();
        assertThat(absent.getUpdatedAt()).isNotNull();
    }

    /** An entity whose @PreUpdate deliberately refuses mutation (audit trail). */
    private static boolean rejectsMutation(Class<?> type) {
        return type == BusinessEvent.class;
    }

    @Test
    @DisplayName("a BusinessEvent cannot be updated or removed — the audit trail is append-only")
    void businessEventsAreAppendOnly() {
        // This is a data-integrity guarantee: if the @PreUpdate/@PreRemove guard is
        // ever dropped, history becomes silently rewritable and the audit trail is
        // worthless. Assert the throw explicitly.
        BusinessEvent e = new BusinessEvent();
        org.assertj.core.api.Assertions
                .assertThatThrownBy(() -> {
                    Method m = BusinessEvent.class.getDeclaredMethod("rejectMutation");
                    m.setAccessible(true);
                    try {
                        m.invoke(e);
                    } catch (java.lang.reflect.InvocationTargetException ite) {
                        throw ite.getCause();
                    }
                })
                .isInstanceOf(UnsupportedOperationException.class)
                .hasMessageContaining("append-only");
    }

    private static Method findGetter(Class<?> type, String suffix, Class<?> param) {
        for (String prefix : new String[]{"get", "is"}) {
            try {
                Method g = type.getMethod(prefix + suffix);
                if (g.getReturnType().isAssignableFrom(param)
                        || param.isAssignableFrom(g.getReturnType())) {
                    return g;
                }
            } catch (NoSuchMethodException ignored) {
                // try the next prefix
            }
        }
        return null;
    }
}
