/**
 * Ardur Appraisal - Main JavaScript
 * Premium interactions and utilities
 */

// ============================================
// Global Configuration
// ============================================
const ArdurApp = {
    config: {
        apiBase: '/api',
        refreshInterval: 30000, // 30 seconds
        toastDuration: 4000
    },
    state: {
        isLoading: false,
        currentUser: null
    }
};

// ============================================
// Utility Functions
// ============================================
const Utils = {
    /**
     * Format date to readable string
     */
    formatDate(dateString, format = 'default') {
        const date = new Date(dateString);
        const options = {
            default: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' },
            short: { month: 'short', day: 'numeric' },
            time: { hour: '2-digit', minute: '2-digit' }
        };
        return date.toLocaleDateString('en-US', options[format] || options.default);
    },

    /**
     * Format file size to readable string
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    /**
     * Debounce function
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Generate random ID
     */
    generateId() {
        return 'id_' + Math.random().toString(36).substr(2, 9);
    },

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// ============================================
// Toast Notifications
// ============================================
const Toast = {
    container: null,

    init() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        this.container.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 12px;
        `;
        document.body.appendChild(this.container);
    },

    show(message, type = 'info', duration = ArdurApp.config.toastDuration) {
        if (!this.container) this.init();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-icon">${this.getIcon(type)}</div>
            <div class="toast-message">${Utils.escapeHtml(message)}</div>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        this.container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });

        // Auto remove
        setTimeout(() => {
            toast.classList.remove('toast-visible');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    getIcon(type) {
        const icons = {
            success: '<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>',
            error: '<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>',
            warning: '<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>',
            info: '<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
        };
        return icons[type] || icons.info;
    },

    success(message) { this.show(message, 'success'); },
    error(message) { this.show(message, 'error'); },
    warning(message) { this.show(message, 'warning'); },
    info(message) { this.show(message, 'info'); }
};

// ============================================
// Modal Manager
// ============================================
const Modal = {
    open(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
            
            // Focus first input
            const firstInput = modal.querySelector('input, select, textarea');
            if (firstInput) setTimeout(() => firstInput.focus(), 100);
        }
    },

    close(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        }
    },

    closeAll() {
        document.querySelectorAll('.modal-overlay.active').forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    },

    closeOnOverlay(event, modalId) {
        if (event.target.classList.contains('modal-overlay')) {
            this.close(modalId);
        }
    }
};

// ============================================
// API Client
// ============================================
const API = {
    async request(endpoint, options = {}) {
        const url = `${ArdurApp.config.apiBase}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json'
            }
        };

        try {
            ArdurApp.state.isLoading = true;
            const response = await fetch(url, { ...defaultOptions, ...options });
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({ error: 'Request failed' }));
                throw new Error(error.error || error.message || 'Request failed');
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        } finally {
            ArdurApp.state.isLoading = false;
        }
    },

    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },

    post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },

    put(endpoint, data) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
};

// ============================================
// File Upload Handler
// ============================================
const FileUpload = {
    init(dropZoneId, fileInputId, options = {}) {
        const dropZone = document.getElementById(dropZoneId);
        const fileInput = document.getElementById(fileInputId);
        
        if (!dropZone || !fileInput) return;

        const config = {
            onFileSelect: options.onFileSelect || (() => {}),
            onUploadProgress: options.onUploadProgress || (() => {}),
            onUploadComplete: options.onUploadComplete || (() => {}),
            onUploadError: options.onUploadError || ((err) => Toast.error(err.message)),
            accept: options.accept || '.zip',
            maxSize: options.maxSize || 100 * 1024 * 1024 // 100MB
        };

        // Click to browse
        dropZone.addEventListener('click', () => fileInput.click());

        // File input change
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFile(e.target.files[0], config);
            }
        });

        // Drag and drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                this.handleFile(e.dataTransfer.files[0], config);
            }
        });

        return { dropZone, fileInput, config };
    },

    handleFile(file, config) {
        // Validate file type
        if (config.accept && !file.name.toLowerCase().endsWith(config.accept.replace('*', ''))) {
            Toast.error(`Please select a ${config.accept} file`);
            return false;
        }

        // Validate file size
        if (file.size > config.maxSize) {
            Toast.error(`File size exceeds ${Utils.formatFileSize(config.maxSize)} limit`);
            return false;
        }

        config.onFileSelect(file);
        return true;
    },

    async upload(formElement, progressCallback) {
        const formData = new FormData(formElement);
        
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const progress = Math.round((e.loaded / e.total) * 100);
                    if (progressCallback) progressCallback(progress);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        reject(new Error(error.error || 'Upload failed'));
                    } catch {
                        reject(new Error('Upload failed'));
                    }
                }
            });

            xhr.addEventListener('error', () => reject(new Error('Network error')));
            
            xhr.open('POST', formElement.action);
            xhr.send(formData);
        });
    }
};

// ============================================
// Table Utilities
// ============================================
const Table = {
    /**
     * Initialize sortable table headers
     */
    makeSortable(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;

        const headers = table.querySelectorAll('th[data-sortable]');
        headers.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => {
                const column = header.dataset.sortable;
                const currentOrder = header.dataset.order || 'asc';
                const newOrder = currentOrder === 'asc' ? 'desc' : 'asc';
                
                // Update header
                headers.forEach(h => h.removeAttribute('data-order'));
                header.dataset.order = newOrder;

                // Sort rows
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                
                rows.sort((a, b) => {
                    const aVal = a.querySelector(`td:nth-child(${header.cellIndex + 1})`).textContent;
                    const bVal = b.querySelector(`td:nth-child(${header.cellIndex + 1})`).textContent;
                    return newOrder === 'asc' 
                        ? aVal.localeCompare(bVal) 
                        : bVal.localeCompare(aVal);
                });

                rows.forEach(row => tbody.appendChild(row));
            });
        });
    },

    /**
     * Initialize table search
     */
    addSearch(tableId, searchInputId) {
        const table = document.getElementById(tableId);
        const searchInput = document.getElementById(searchInputId);
        if (!table || !searchInput) return;

        searchInput.addEventListener('input', Utils.debounce((e) => {
            const query = e.target.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        }, 300));
    }
};

// ============================================
// Real-time Status Updates
// ============================================
const StatusPoller = {
    intervals: {},

    start(key, callback, interval = ArdurApp.config.refreshInterval) {
        this.stop(key);
        this.intervals[key] = setInterval(callback, interval);
        callback(); // Run immediately
    },

    stop(key) {
        if (this.intervals[key]) {
            clearInterval(this.intervals[key]);
            delete this.intervals[key];
        }
    },

    stopAll() {
        Object.keys(this.intervals).forEach(key => this.stop(key));
    }
};

// ============================================
// Charts Helper (Simple Bar Chart)
// ============================================
const Charts = {
    createBar(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const maxValue = Math.max(...data.map(d => d.value));
        const config = {
            barColor: options.barColor || 'var(--color-accent-gradient)',
            height: options.height || 200,
            ...options
        };

        container.innerHTML = `
            <div class="chart-bar-container" style="height: ${config.height}px; display: flex; align-items: flex-end; gap: 8px; padding: 16px 0;">
                ${data.map(d => `
                    <div class="chart-bar-wrapper" style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8px;">
                        <div class="chart-bar" style="
                            width: 100%;
                            height: ${(d.value / maxValue) * 100}%;
                            min-height: 4px;
                            background: ${config.barColor};
                            border-radius: 4px 4px 0 0;
                            transition: height 0.3s ease;
                        "></div>
                        <span class="chart-label text-xs text-muted">${d.label}</span>
                        <span class="chart-value text-sm">${d.value}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }
};

// ============================================
// Theme Manager
// ============================================
const Theme = {
    init() {
        const saved = localStorage.getItem('theme');
        if (saved) {
            document.documentElement.setAttribute('data-theme', saved);
        }
    },

    toggle() {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    }
};

// ============================================
// Keyboard Shortcuts
// ============================================
const Keyboard = {
    shortcuts: {},

    register(key, callback, description = '') {
        this.shortcuts[key] = { callback, description };
    },

    init() {
        document.addEventListener('keydown', (e) => {
            // Ignore when typing in inputs
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

            const key = `${e.ctrlKey ? 'ctrl+' : ''}${e.shiftKey ? 'shift+' : ''}${e.key.toLowerCase()}`;
            
            if (this.shortcuts[key]) {
                e.preventDefault();
                this.shortcuts[key].callback();
            }
        });

        // Escape closes modals
        this.register('escape', () => Modal.closeAll(), 'Close modals');
    }
};

// ============================================
// Page-specific Initializers
// ============================================
const Pages = {
    dashboard() {
        // Auto-refresh dashboard stats
        StatusPoller.start('dashboard', async () => {
            try {
                const role = document.body.dataset.role;
                let endpoint = '/admin/dashboard';
                if (role === 'CLIENT') endpoint = '/client/dashboard';
                if (role === 'REVIEWER') endpoint = '/reviewer/dashboard';
                
                // Could update stats here via API
            } catch (error) {
                console.error('Failed to refresh dashboard:', error);
            }
        }, 60000);
    },

    batchStatus(batchId) {
        StatusPoller.start('batchStatus', async () => {
            try {
                const status = await API.get(`/client/batches/${batchId}/status`);
                // Update UI with new status
                const statusBadge = document.getElementById('batchStatusBadge');
                const progressBar = document.getElementById('batchProgress');
                
                if (statusBadge) statusBadge.textContent = status.status;
                if (progressBar && status.totalFiles > 0) {
                    const progress = (status.completedFiles / status.totalFiles) * 100;
                    progressBar.style.width = `${progress}%`;
                }
            } catch (error) {
                console.error('Failed to refresh batch status:', error);
            }
        }, 10000); // More frequent for batch status
    }
};

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    Toast.init();
    Theme.init();
    Keyboard.init();

    // Initialize modals
    document.querySelectorAll('[data-modal-open]').forEach(btn => {
        btn.addEventListener('click', () => Modal.open(btn.dataset.modalOpen));
    });

    document.querySelectorAll('[data-modal-close]').forEach(btn => {
        btn.addEventListener('click', () => Modal.close(btn.dataset.modalClose));
    });

    // Initialize confirmation dialogs
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', (e) => {
            if (!confirm(form.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });

    // Auto-hide alerts after 5 seconds
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // Mobile sidebar toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.querySelector('.sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }

    console.log('🚀 Ardur Appraisal initialized');
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    StatusPoller.stopAll();
});

// Export for global access
window.ArdurApp = ArdurApp;
window.Utils = Utils;
window.Toast = Toast;
window.Modal = Modal;
window.API = API;
window.FileUpload = FileUpload;
window.Table = Table;
window.StatusPoller = StatusPoller;
window.Charts = Charts;
window.Pages = Pages;
