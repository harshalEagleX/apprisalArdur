package com.apprisal.common.util;

import java.time.LocalDateTime;
import java.time.ZoneId;

public final class AppTime {

    public static final ZoneId ZONE = ZoneId.of("Asia/Kolkata");

    private AppTime() {
    }

    public static LocalDateTime now() {
        return LocalDateTime.now(ZONE);
    }
}
