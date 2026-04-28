package com.apprisal.common.audit;

import com.apprisal.common.security.UserPrincipal;
import org.hibernate.envers.RevisionListener;
import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class AppRevisionListener implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AppRevisionEntity rev = (AppRevisionEntity) revisionEntity;
        rev.setCorrelationId(MDC.get("correlationId"));

        try {
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            if (auth != null && auth.getPrincipal() instanceof UserPrincipal up) {
                rev.setUsername(up.getUsername());
            }
        } catch (Exception ignored) {}

        try {
            String ip = MDC.get("clientIp");
            if (ip != null) rev.setIpAddress(ip);
        } catch (Exception ignored) {}
    }
}
