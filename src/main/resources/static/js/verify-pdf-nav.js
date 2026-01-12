/**
 * PDF Navigation and Highlighting Module
 * Computes page mapping on-demand from OCR data (no database storage)
 * Handles rule card clicks and coordinates with PDF viewer
 */

// Section keyword mappings for rule-to-page lookup
const RULE_SECTION_MAP = {
    'S-': {
        section: 'subject',
        keywords: ['subject', 'property address', 'borrower', 'owner of public record', 'legal description']
    },
    'C-': {
        section: 'contract',
        keywords: ['contract', 'sale price', 'seller', 'purchase', 'assignment type']
    },
    'N-': {
        section: 'neighborhood',
        keywords: ['neighborhood', 'location', 'built-up', 'growth', 'land use']
    },
    'Site': {
        section: 'site',
        keywords: ['site', 'dimensions', 'area', 'zoning', 'utilities', 'flood zone']
    },
    'Imp': {
        section: 'improvements',
        keywords: ['improvements', 'foundation', 'exterior walls', 'roof', 'interior']
    },
    'SC-': {
        section: 'sales_comparison',
        keywords: ['sales comparison', 'comparable', 'subject property', 'adjustment', 'grid']
    }
};

// Page index cache (loaded from OCR data)
let pageIndex = null;

/**
 * Initialize PDF navigation system
 */
function initPdfNavigation() {
    // Load page index from embedded data
    loadPageIndex();

    // Setup event delegation on rules container
    const rulesContainer = document.getElementById('rulesContainer');
    if (!rulesContainer) {
        console.warn('PDF Navigation: rulesContainer not found');
        return;
    }

    // Event delegation - single listener for all rule cards
    rulesContainer.addEventListener('click', handleRuleCardClick);

    console.log('PDF Navigation initialized');
}

/**
 * Load page index from embedded OCR data
 */
function loadPageIndex() {
    const pageIndexEl = document.getElementById('pageIndexData');
    if (pageIndexEl) {
        try {
            pageIndex = JSON.parse(pageIndexEl.textContent);
            console.log('Loaded page index with', Object.keys(pageIndex).length, 'pages');
        } catch (e) {
            console.warn('Failed to parse page index:', e);
            pageIndex = {};
        }
    } else {
        console.warn('Page index data element not found');
        pageIndex = {};
    }
}

/**
 * Find page number for a rule using keyword matching
 */
function findPageForRule(ruleId) {
    if (!pageIndex || Object.keys(pageIndex).length === 0) {
        return { page: 1, section: null };
    }

    // Find matching rule section
    let sectionInfo = null;
    for (const [prefix, info] of Object.entries(RULE_SECTION_MAP)) {
        if (ruleId.startsWith(prefix)) {
            sectionInfo = info;
            break;
        }
    }

    if (!sectionInfo) {
        return { page: 1, section: null };
    }

    // Score each page by keyword matches
    let bestPage = 1;
    let bestScore = 0;

    for (const [pageNum, text] of Object.entries(pageIndex)) {
        const lowerText = text.toLowerCase();
        let score = 0;

        for (const keyword of sectionInfo.keywords) {
            if (lowerText.includes(keyword)) {
                score++;
            }
        }

        // Short-circuit on high confidence
        if (score >= 3) {
            return { page: parseInt(pageNum), section: sectionInfo.section };
        }

        if (score > bestScore) {
            bestScore = score;
            bestPage = parseInt(pageNum);
        }
    }

    return {
        page: bestScore > 0 ? bestPage : 1,
        section: sectionInfo.section
    };
}

/**
 * Handle rule card click
 */
function handleRuleCardClick(e) {
    // Don't trigger if clicking buttons, inputs
    if (e.target.closest('.decision-btns, .btn, input, textarea, summary')) {
        return;
    }

    // Find rule card
    const card = e.target.closest('.verify-item:not(.overall-notes)');
    if (!card) return;

    const ruleId = card.dataset.ruleId;
    const status = card.dataset.status;

    if (!ruleId) return;

    // Find page for this rule
    const { page, section } = findPageForRule(ruleId);

    // Navigate and highlight
    navigateToPdfPage(page, status, ruleId, section);
}

/**
 * Navigate PDF to page and add highlight
 */
async function navigateToPdfPage(pageNum, status, ruleId, section) {
    const viewer = window.getPDFViewer ? window.getPDFViewer() : null;

    if (!viewer) {
        console.warn('PDF Viewer not initialized');
        return;
    }

    // Navigate to page
    await viewer.goToPage(pageNum);

    // Add highlight
    viewer.addHighlight(status, ruleId, section);

    // Show toast notification
    const message = section
        ? `${section.charAt(0).toUpperCase() + section.slice(1)} Section → Page ${pageNum}`
        : `Navigating to page ${pageNum}`;

    if (typeof Toast !== 'undefined' && Toast.info) {
        Toast.info(message);
    } else {
        console.log(message);
    }

    // Log to audit API
    logHighlightAction(ruleId, pageNum, status, section);
}

/**
 * Log highlight action to audit API
 */
function logHighlightAction(ruleId, pageNum, status, section) {
    // Get file ID from URL or data attribute
    const fileId = document.body.dataset.fileId ||
        window.location.pathname.split('/').pop();

    const auditData = {
        fileId: fileId,
        ruleId: ruleId,
        pageNumber: pageNum,
        status: status,
        section: section,
        timestamp: new Date().toISOString()
    };

    // Non-blocking POST to audit endpoint
    fetch('/api/audit/highlight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(auditData)
    }).catch(err => {
        console.warn('Audit log failed:', err);
    });

    // Also log to console
    console.log('AUDIT:', `Rule ${ruleId} viewed on page ${pageNum} (${status})`);
}

// Export functions
window.initPdfNavigation = initPdfNavigation;
window.navigateToPdfPage = navigateToPdfPage;
window.findPageForRule = findPageForRule;
