package com.apprisal.exception;

/**
 * Exception thrown when a user doesn't have permission to access a resource.
 */
public class AccessDeniedException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    public AccessDeniedException(String message) {
        super(message);
    }

    public AccessDeniedException() {
        super("You do not have permission to access this resource");
    }
}
