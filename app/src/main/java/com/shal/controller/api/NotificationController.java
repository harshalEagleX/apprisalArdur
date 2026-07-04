package com.shal.controller.api;

import com.shal.common.entity.Notification;
import com.shal.common.security.UserPrincipal;
import com.shal.common.service.NotificationService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The current user's in-app notifications. Any authenticated user (admin or
 * reviewer) reads and marks their own — a user can only ever see their own rows
 * because every query is scoped to the authenticated principal's id.
 */
@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @GetMapping
    public ResponseEntity<?> list(@RequestParam(defaultValue = "20") int limit,
                                  @AuthenticationPrincipal UserPrincipal principal) {
        Long uid = principal.getUser().getId();
        int cappedLimit = Math.max(1, Math.min(limit, 100));
        List<Map<String, Object>> items = notificationService.recentFor(uid, cappedLimit).stream()
                .map(NotificationController::toDto).toList();
        return ResponseEntity.ok(Map.of(
                "items", items,
                "unreadCount", notificationService.unreadCount(uid)));
    }

    @PostMapping("/{id}/read")
    public ResponseEntity<?> markRead(@PathVariable Long id,
                                      @AuthenticationPrincipal UserPrincipal principal) {
        boolean ok = notificationService.markRead(id, principal.getUser().getId());
        return ok ? ResponseEntity.ok(Map.of("success", true)) : ResponseEntity.notFound().build();
    }

    @PostMapping("/read-all")
    public ResponseEntity<?> markAllRead(@AuthenticationPrincipal UserPrincipal principal) {
        int marked = notificationService.markAllRead(principal.getUser().getId());
        return ResponseEntity.ok(Map.of("markedRead", marked));
    }

    private static Map<String, Object> toDto(Notification n) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", n.getId());
        m.put("type", n.getType());
        m.put("title", n.getTitle());
        m.put("message", n.getMessage());
        m.put("link", n.getLink());
        m.put("read", n.isRead());
        m.put("createdAt", n.getCreatedAt() != null ? n.getCreatedAt().toString() : null);
        return m;
    }
}
