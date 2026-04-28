package com.apprisal.exception;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import com.apprisal.common.exception.AccessDeniedException;
import com.apprisal.common.exception.ResourceNotFoundException;
import com.apprisal.common.exception.ValidationException;
import com.apprisal.common.exception.BatchProcessingException;

/**
 * Global exception handler for web (Thymeleaf) controllers.
 * Provides user-friendly error messages and proper redirects.
 */
@ControllerAdvice(basePackages = "com.apprisal.controller", basePackageClasses = {})
public class GlobalWebExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalWebExceptionHandler.class);

    @ExceptionHandler(ResourceNotFoundException.class)
    public String handleResourceNotFound(ResourceNotFoundException ex, RedirectAttributes redirectAttributes) {
        log.warn("Resource not found: {}", ex.getMessage());
        redirectAttributes.addFlashAttribute("error", ex.getMessage());
        return "redirect:/";
    }

    @ExceptionHandler(ValidationException.class)
    public String handleValidation(ValidationException ex, RedirectAttributes redirectAttributes) {
        log.warn("Validation failed: {}", ex.getMessage());
        redirectAttributes.addFlashAttribute("error", ex.getMessage());
        return "redirect:/";
    }

    @ExceptionHandler(AccessDeniedException.class)
    public String handleAccessDenied(AccessDeniedException ex, RedirectAttributes redirectAttributes) {
        log.warn("Access denied: {}", ex.getMessage());
        redirectAttributes.addFlashAttribute("error", "Access denied: " + ex.getMessage());
        return "redirect:/";
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public String handleMaxUploadSize(MaxUploadSizeExceededException ex, RedirectAttributes redirectAttributes) {
        log.warn("File upload too large: {}", ex.getMessage());
        redirectAttributes.addFlashAttribute("error", "File size exceeds maximum allowed limit (100MB)");
        return "redirect:/client/upload";
    }

    @ExceptionHandler(BatchProcessingException.class)
    public String handleBatchProcessing(BatchProcessingException ex, RedirectAttributes redirectAttributes) {
        log.error("Batch processing error: {}", ex.getMessage(), ex);
        redirectAttributes.addFlashAttribute("error", "Batch processing failed: " + ex.getMessage());
        return "redirect:/client/dashboard";
    }

    // Note: Generic exceptions are handled by Spring's default error handling
    // which renders the error templates (error/500.html, etc.)
}
