package com.apprisal.config;

import com.apprisal.batch.service.OperatorSessionService;
import com.apprisal.common.security.UserPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.LogoutSuccessEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * Listens to Spring Security authentication events and drives operator session tracking.
 */
@Component
public class SecurityEventListener {

    private static final Logger log = LoggerFactory.getLogger(SecurityEventListener.class);

    private final OperatorSessionService sessionService;

    public SecurityEventListener(OperatorSessionService sessionService) {
        this.sessionService = sessionService;
    }

    @EventListener
    public void onLoginSuccess(AuthenticationSuccessEvent event) {
        if (!(event.getAuthentication().getPrincipal() instanceof UserPrincipal up)) return;

        String ip        = resolveIp();
        String userAgent = resolveUserAgent();

        try {
            sessionService.startSession(up.getUser(), ip, userAgent);
        } catch (Exception e) {
            log.warn("Could not start operator session for {}: {}", up.getUsername(), e.getMessage());
        }
    }

    @EventListener
    public void onLoginFailure(AbstractAuthenticationFailureEvent event) {
        log.warn("Login failed for principal={} reason={}",
                event.getAuthentication().getName(),
                event.getException().getMessage());
    }

    @EventListener
    public void onLogout(LogoutSuccessEvent event) {
        if (!(event.getAuthentication().getPrincipal() instanceof UserPrincipal up)) return;
        try {
            sessionService.findActive(up.getUser().getId())
                          .ifPresent(s -> sessionService.endSession(s.getSessionToken()));
        } catch (Exception e) {
            log.warn("Could not end operator session: {}", e.getMessage());
        }
    }

    private String resolveIp() {
        try {
            var attrs = (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
            HttpServletRequest req = attrs.getRequest();
            String xff = req.getHeader("X-Forwarded-For");
            return xff != null ? xff.split(",")[0].trim() : req.getRemoteAddr();
        } catch (Exception e) { return "unknown"; }
    }

    private String resolveUserAgent() {
        try {
            var attrs = (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
            String ua = attrs.getRequest().getHeader("User-Agent");
            return ua != null ? ua.substring(0, Math.min(ua.length(), 512)) : "unknown";
        } catch (Exception e) { return "unknown"; }
    }
}
