/**
 * PDF Viewer Controller - Using PDF.js for reliable rendering and navigation
 * Features:
 * - Page navigation API
 * - Canvas-based rendering (allows overlays)
 * - Zoom controls
 * - Audit logging integration
 */

class PDFViewerController {
    constructor(containerId, pdfUrl) {
        this.containerId = containerId;
        this.pdfUrl = pdfUrl;
        this.pdfDoc = null;
        this.currentPage = 1;
        this.totalPages = 0;
        this.scale = 1.0;
        this.rendering = false;
        this.pendingPage = null;

        // DOM elements
        this.container = document.getElementById(containerId);
        this.canvas = null;
        this.ctx = null;
        this.highlightOverlay = null;

        // Callbacks
        this.onPageChange = null;
        this.onLoad = null;
    }

    /**
     * Initialize the viewer
     */
    async init() {
        if (!this.container) {
            console.error('PDF container not found:', this.containerId);
            return false;
        }

        // Create canvas and overlay
        this.setupDOM();

        // Load PDF document
        try {
            await this.loadDocument();
            return true;
        } catch (error) {
            console.error('Failed to load PDF:', error);
            this.showError('Failed to load PDF document');
            return false;
        }
    }

    /**
     * Setup DOM elements for PDF rendering
     */
    setupDOM() {
        // Clear container
        this.container.innerHTML = '';

        // Create canvas
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'pdfCanvas';
        this.canvas.className = 'pdf-canvas';
        this.ctx = this.canvas.getContext('2d');

        // Create highlight overlay
        this.highlightOverlay = document.createElement('div');
        this.highlightOverlay.id = 'pdfHighlightOverlay';
        this.highlightOverlay.className = 'pdf-highlight-overlay';

        // Create controls
        const controls = document.createElement('div');
        controls.className = 'pdf-controls';
        controls.innerHTML = `
            <button type="button" class="pdf-ctrl-btn" id="pdfPrevPage" title="Previous Page">
                <i class="bi bi-chevron-left"></i>
            </button>
            <span class="pdf-page-info">
                <span id="pdfCurrentPage">1</span> / <span id="pdfTotalPages">?</span>
            </span>
            <button type="button" class="pdf-ctrl-btn" id="pdfNextPage" title="Next Page">
                <i class="bi bi-chevron-right"></i>
            </button>
            <span class="pdf-divider"></span>
            <button type="button" class="pdf-ctrl-btn" id="pdfZoomOut" title="Zoom Out">
                <i class="bi bi-zoom-out"></i>
            </button>
            <span class="pdf-zoom-info" id="pdfZoomLevel">100%</span>
            <button type="button" class="pdf-ctrl-btn" id="pdfZoomIn" title="Zoom In">
                <i class="bi bi-zoom-in"></i>
            </button>
        `;

        // Wrapper for canvas and overlay
        const canvasWrapper = document.createElement('div');
        canvasWrapper.className = 'pdf-canvas-wrapper';
        canvasWrapper.appendChild(this.canvas);
        canvasWrapper.appendChild(this.highlightOverlay);

        // Append to container
        this.container.appendChild(controls);
        this.container.appendChild(canvasWrapper);

        // Bind control events
        this.bindControls();
    }

    /**
     * Bind control button events
     */
    bindControls() {
        const prevBtn = document.getElementById('pdfPrevPage');
        const nextBtn = document.getElementById('pdfNextPage');
        const zoomInBtn = document.getElementById('pdfZoomIn');
        const zoomOutBtn = document.getElementById('pdfZoomOut');

        if (prevBtn) prevBtn.addEventListener('click', () => this.prevPage());
        if (nextBtn) nextBtn.addEventListener('click', () => this.nextPage());
        if (zoomInBtn) zoomInBtn.addEventListener('click', () => this.zoomIn());
        if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => this.zoomOut());
    }

    /**
     * Load PDF document using PDF.js
     */
    async loadDocument() {
        // Ensure PDF.js is loaded
        if (typeof pdfjsLib === 'undefined') {
            throw new Error('PDF.js library not loaded');
        }

        // Set worker source
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

        // Load document
        const loadingTask = pdfjsLib.getDocument(this.pdfUrl);
        this.pdfDoc = await loadingTask.promise;
        this.totalPages = this.pdfDoc.numPages;

        // Update UI
        const totalPagesEl = document.getElementById('pdfTotalPages');
        if (totalPagesEl) totalPagesEl.textContent = this.totalPages;

        // Render first page
        await this.renderPage(1);

        // Callback
        if (this.onLoad) {
            this.onLoad(this.totalPages);
        }
    }

    /**
     * Render a specific page
     */
    async renderPage(pageNum) {
        if (!this.pdfDoc) return;

        // Handle concurrent render requests
        if (this.rendering) {
            this.pendingPage = pageNum;
            return;
        }
        this.rendering = true;

        try {
            // Get page
            const page = await this.pdfDoc.getPage(pageNum);

            // Calculate scale to fit container width
            const containerWidth = this.container.clientWidth - 40; // padding
            const viewport = page.getViewport({ scale: 1.0 });
            const fitScale = containerWidth / viewport.width;
            const scaledViewport = page.getViewport({ scale: fitScale * this.scale });

            // Set canvas size
            this.canvas.height = scaledViewport.height;
            this.canvas.width = scaledViewport.width;

            // Render
            const renderContext = {
                canvasContext: this.ctx,
                viewport: scaledViewport
            };

            await page.render(renderContext).promise;

            // Update current page
            this.currentPage = pageNum;
            const currentPageEl = document.getElementById('pdfCurrentPage');
            if (currentPageEl) currentPageEl.textContent = pageNum;

            // Callback
            if (this.onPageChange) {
                this.onPageChange(pageNum);
            }

        } finally {
            this.rendering = false;

            // Handle pending render request
            if (this.pendingPage !== null && this.pendingPage !== pageNum) {
                const pending = this.pendingPage;
                this.pendingPage = null;
                await this.renderPage(pending);
            }
        }
    }

    /**
     * Navigate to specific page (PUBLIC API)
     */
    async goToPage(pageNum) {
        if (pageNum < 1) pageNum = 1;
        if (pageNum > this.totalPages) pageNum = this.totalPages;

        await this.renderPage(pageNum);

        // Scroll canvas into view
        this.canvas.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * Navigate to previous page
     */
    async prevPage() {
        if (this.currentPage > 1) {
            await this.goToPage(this.currentPage - 1);
        }
    }

    /**
     * Navigate to next page
     */
    async nextPage() {
        if (this.currentPage < this.totalPages) {
            await this.goToPage(this.currentPage + 1);
        }
    }

    /**
     * Zoom in
     */
    zoomIn() {
        if (this.scale < 3.0) {
            this.scale += 0.25;
            this.updateZoom();
        }
    }

    /**
     * Zoom out
     */
    zoomOut() {
        if (this.scale > 0.5) {
            this.scale -= 0.25;
            this.updateZoom();
        }
    }

    /**
     * Update zoom level
     */
    updateZoom() {
        const zoomLevelEl = document.getElementById('pdfZoomLevel');
        if (zoomLevelEl) zoomLevelEl.textContent = Math.round(this.scale * 100) + '%';
        this.renderPage(this.currentPage);
    }

    /**
     * Add highlight overlay (PUBLIC API)
     */
    addHighlight(status, ruleId, section) {
        if (!this.highlightOverlay) return;

        // Clear existing highlights
        this.clearHighlights();

        // Create highlight element
        const highlight = document.createElement('div');
        highlight.className = `pdf-page-highlight ${status.toLowerCase()}`;

        // Tooltip
        const tooltip = section
            ? `${section.toUpperCase()} - Rule ${ruleId}`
            : `Rule ${ruleId}`;
        highlight.title = tooltip;

        // Add to overlay
        this.highlightOverlay.appendChild(highlight);

        // Auto-remove after animation (5 seconds)
        setTimeout(() => {
            highlight.style.opacity = '0';
            setTimeout(() => highlight.remove(), 300);
        }, 5000);
    }

    /**
     * Clear all highlights
     */
    clearHighlights() {
        if (this.highlightOverlay) {
            this.highlightOverlay.innerHTML = '';
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        if (this.container) {
            this.container.innerHTML = `
                <div class="pdf-error">
                    <i class="bi bi-exclamation-triangle"></i>
                    <p>${message}</p>
                </div>
            `;
        }
    }
}

// Global instance
let pdfViewer = null;

/**
 * Initialize PDF viewer with given URL
 */
async function initPDFViewer(pdfUrl) {
    pdfViewer = new PDFViewerController('pdfViewerContainer', pdfUrl);
    const success = await pdfViewer.init();

    if (success) {
        console.log('PDF Viewer initialized successfully');
    }

    return pdfViewer;
}

// Export for global access
window.PDFViewerController = PDFViewerController;
window.initPDFViewer = initPDFViewer;
window.getPDFViewer = () => pdfViewer;
