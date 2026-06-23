package com.shal.common.util;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Small helper for cross-service timeline logs.
 *
 * Keep messages as key=value pairs so Java, Python, and browser-console logs can
 * be compared by batch_id/correlation_id without needing a separate log pipeline.
 */
public final class TimelineLog {

    private static final long PID = ProcessHandle.current().pid();
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    private TimelineLog() {
    }

    public static OffsetDateTime now() {
        return OffsetDateTime.now(AppTime.ZONE);
    }

    public static String event(String flow, String event, Object... keyValues) {
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("flow", flow);
        fields.put("event", event);
        fields.put("ist", FORMATTER.format(now()));
        fields.put("pid", PID);

        for (int i = 0; i + 1 < keyValues.length; i += 2) {
            fields.put(String.valueOf(keyValues[i]), keyValues[i + 1]);
        }

        return fields.entrySet().stream()
                .map(entry -> entry.getKey() + "=" + sanitize(entry.getValue()))
                .collect(Collectors.joining(" "));
    }

    public static long elapsedMs(long startedNanos) {
        return Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }

    private static String sanitize(Object value) {
        if (value == null) {
            return "null";
        }
        String text = String.valueOf(value).replace('\n', ' ').replace('\r', ' ').trim();
        if (text.isEmpty()) {
            return "\"\"";
        }
        if (text.indexOf(' ') >= 0 || text.indexOf('=') >= 0) {
            return "\"" + text.replace("\"", "'") + "\"";
        }
        return text;
    }
}
