/**
 * Verification Page JavaScript
 * Handles verification decisions, filtering, auto-save, and form submission
 */

// State management
const state = {
    decisions: {},      // ruleResultId -> { decision, comment }
    filter: 'all',
    qcResultId: null,
    totalToVerify: 0
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Get QC Result ID
    const qcResultIdEl = document.getElementById('qcResultId');
    state.qcResultId = qcResultIdEl ? qcResultIdEl.value : null;

    // Count items that need verification
    state.totalToVerify = document.querySelectorAll('.verify-item[data-review-required="true"]').length;
    console.log(`Verification page loaded: ${state.totalToVerify} items to verify`);

    // Load persisted state
    loadPersistedState();

    // Initialize filter buttons
    initFilters();

    // Initialize existing decisions from DOM
    initExistingDecisions();

    // Update submit button state
    updateSubmitButton();

    // Save scroll position on scroll
    const panelBody = document.querySelector('.panel-body');
    if (panelBody) {
        panelBody.addEventListener('scroll', debounce(() => {
            persistState();
        }, 500));
    }
});

/**
 * Initialize filter button event handlers
 */
function initFilters() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const filter = btn.dataset.filter;
            applyFilter(filter);

            // Update active state
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Persist filter state
            state.filter = filter;
            persistState();
        });
    });
}

/**
 * Apply filter to show/hide rule cards (frontend-only, no API calls)
 */
function applyFilter(filter) {
    document.querySelectorAll('.verify-item:not(.overall-notes)').forEach(item => {
        const status = (item.dataset.status || '').toUpperCase();
        const reviewRequired = item.dataset.reviewRequired === 'true';
        let visible = false;

        switch (filter) {
            case 'all-items':
                visible = true;
                break;
            case 'pass':
                visible = status === 'PASS';
                break;
            case 'manual-pass':
                visible = status === 'MANUAL_PASS';
                break;
            case 'fail':
                visible = status === 'FAIL' || status === 'ERROR';
                break;
            case 'to-verify':
                // Only show if needs review AND not yet decided (not MANUAL_PASS or FAIL)
                visible = reviewRequired && status !== 'MANUAL_PASS' && status !== 'FAIL';
                break;
            default:
                visible = true;
        }

        item.style.display = visible ? 'block' : 'none';
    });
}

/**
 * Initialize decisions from pre-filled values in DOM
 */
function initExistingDecisions() {
    document.querySelectorAll('input[id^="decision_"]').forEach(input => {
        if (input.value) {
            const ruleId = input.id.replace('decision_', '');
            const commentEl = document.getElementById('comment_' + ruleId);
            state.decisions[ruleId] = {
                decision: input.value.toUpperCase(),
                comment: commentEl ? commentEl.value : ''
            };
        }
    });
}

/**
 * Select a decision for a verification item (with auto-save)
 * @param {number} ruleResultId - The rule result ID
 * @param {string} decision - 'PASS' or 'FAIL'
 * @param {HTMLElement} btn - The clicked button
 */
async function selectDecision(ruleResultId, decision, btn) {
    const commentEl = document.getElementById('comment_' + ruleResultId);
    const comment = commentEl ? commentEl.value : '';

    // Update state
    state.decisions[ruleResultId] = { decision, comment };

    // Update hidden input
    const hiddenInput = document.getElementById('decision_' + ruleResultId);
    if (hiddenInput) {
        hiddenInput.value = decision.toLowerCase();
    }

    // Update button states
    const acceptBtn = document.getElementById('accept_' + ruleResultId);
    const rejectBtn = document.getElementById('reject_' + ruleResultId);

    if (acceptBtn) {
        acceptBtn.classList.toggle('active', decision === 'PASS');
    }
    if (rejectBtn) {
        rejectBtn.classList.toggle('active', decision === 'FAIL');
    }

    // Auto-save to backend
    try {
        await saveDecisionToBackend(ruleResultId, decision, comment);
        showAutoSaveIndicator(true);

        // CRITICAL: Update card status and move to correct filter section
        updateCardStatus(ruleResultId, decision);
    } catch (error) {
        console.error('Auto-save failed:', error);
        showAutoSaveIndicator(false);
    }

    // Update submit button state
    updateSubmitButton();

    // Persist state
    persistState();

    console.log(`Decision for rule ${ruleResultId}: ${decision}`);
}

/**
 * Update card status immediately after decision to move it to correct filter section
 */
function updateCardStatus(ruleResultId, decision) {
    // Find the card element
    const card = document.querySelector(`[data-rule-id="${ruleResultId}"]`);
    if (!card) return;

    // Determine new status
    const newStatus = decision === 'PASS' ? 'MANUAL_PASS' : 'FAIL';

    // Update dataset
    card.dataset.status = newStatus;

    // Update CSS classes for styling
    card.classList.remove('pass', 'fail', 'verify', 'error', 'manual_pass');
    card.classList.add(newStatus.toLowerCase().replace('_', '_'));

    // Update status badge
    const statusBadge = card.querySelector('.status-badge');
    if (statusBadge) {
        statusBadge.className = 'status-badge ' + newStatus.toLowerCase().replace('_', '_');
        statusBadge.textContent = newStatus.replace('_', ' ');
    }

    // Reapply current filter to move card to correct section
    const currentFilter = state.filter || 'all-items';
    applyFilter(currentFilter);

    console.log(`Card ${ruleResultId} updated to status: ${newStatus}`);
}

/**
 * Save decision to backend via AJAX (auto-save)
 */
async function saveDecisionToBackend(ruleResultId, decision, comment) {
    const response = await fetch('/api/reviewer/decision/save', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            ruleResultId: parseInt(ruleResultId),
            decision: decision,
            comment: comment || ''
        })
    });

    if (!response.ok) {
        throw new Error('Failed to save decision');
    }

    return await response.json();
}

/**
 * Show auto-save indicator
 */
function showAutoSaveIndicator(success) {
    // Brief visual feedback
    const indicator = document.createElement('div');
    indicator.className = 'auto-save-indicator ' + (success ? 'success' : 'error');
    indicator.innerHTML = success
        ? '<i class="bi bi-check-circle"></i> Saved'
        : '<i class="bi bi-x-circle"></i> Save failed';
    document.body.appendChild(indicator);

    setTimeout(() => {
        indicator.classList.add('fade-out');
        setTimeout(() => indicator.remove(), 300);
    }, 1500);
}

/**
 * Pass all verification items
 */
function passAllItems() {
    document.querySelectorAll('.verify-item[data-review-required="true"]').forEach(item => {
        const ruleId = item.dataset.ruleId;
        if (ruleId) {
            selectDecision(ruleId, 'PASS', null);
        }
    });

    Toast.success('All items marked as passed');
}

/**
 * Update the submit button state based on decisions
 */
function updateSubmitButton() {
    const decidedCount = Object.keys(state.decisions).length;
    const submitBtn = document.getElementById('submitBtn');

    if (submitBtn) {
        const allDecided = decidedCount >= state.totalToVerify && state.totalToVerify > 0;

        if (allDecided) {
            submitBtn.disabled = false;
            submitBtn.classList.remove('btn-secondary');
            submitBtn.classList.add('btn-primary');
        } else {
            submitBtn.disabled = true;
            submitBtn.classList.add('btn-secondary');
            submitBtn.classList.remove('btn-primary');
        }

        // Update helper text
        const helperText = submitBtn.nextElementSibling;
        if (helperText) {
            helperText.textContent = allDecided
                ? `Ready to submit (${decidedCount}/${state.totalToVerify} decisions made)`
                : `Make a decision on all items (${decidedCount}/${state.totalToVerify})`;
        }
    }
}

/**
 * Show pre-submit summary modal
 */
function showSubmitSummary() {
    const tbody = document.getElementById('summaryTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    // Build summary table
    document.querySelectorAll('.verify-item[data-review-required="true"]').forEach(item => {
        const ruleId = item.dataset.ruleId;
        const ruleCode = item.querySelector('.rule-badge')?.textContent || 'N/A';
        const systemStatus = item.dataset.status || 'N/A';
        const decision = state.decisions[ruleId]?.decision || 'N/A';
        const comment = state.decisions[ruleId]?.comment || '';

        // Determine if this is an override
        const isOverride = (systemStatus === 'FAIL' || systemStatus === 'ERROR') && decision === 'PASS';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><span class="rule-badge">${ruleCode}</span></td>
            <td><span class="status-badge ${systemStatus.toLowerCase()}">${systemStatus}</span></td>
            <td><span class="decision-badge ${decision.toLowerCase()}">${decision}</span></td>
            <td>${isOverride ? '<span class="override-badge"><i class="bi bi-exclamation-triangle"></i> Yes</span>' : '-'}</td>
            <td class="comment-cell">${comment || '-'}</td>
        `;
        tbody.appendChild(row);
    });

    // Show modal
    Modal.open('submitModal');
}

/**
 * Confirm and submit the verification form
 */
function confirmSubmit() {
    Modal.close('submitModal');
    document.getElementById('verifyForm').submit();
}

/**
 * Persist state to localStorage
 */
function persistState() {
    if (state.qcResultId) {
        const panelBody = document.querySelector('.panel-body');
        const stateToSave = {
            decisions: state.decisions,
            filter: state.filter,
            scrollPosition: panelBody ? panelBody.scrollTop : 0
        };
        localStorage.setItem(`verify_state_${state.qcResultId}`, JSON.stringify(stateToSave));
    }
}

/**
 * Load persisted state from localStorage
 */
function loadPersistedState() {
    if (state.qcResultId) {
        const savedState = localStorage.getItem(`verify_state_${state.qcResultId}`);
        if (savedState) {
            try {
                const parsed = JSON.parse(savedState);

                // Restore filter
                if (parsed.filter && parsed.filter !== 'all') {
                    const filterBtn = document.querySelector(`[data-filter="${parsed.filter}"]`);
                    if (filterBtn) {
                        filterBtn.click();
                    }
                }

                // Restore scroll position
                if (parsed.scrollPosition) {
                    const panelBody = document.querySelector('.panel-body');
                    if (panelBody) {
                        setTimeout(() => {
                            panelBody.scrollTop = parsed.scrollPosition;
                        }, 100);
                    }
                }

                console.log('Restored persisted state');
            } catch (e) {
                console.error('Failed to restore state:', e);
            }
        }
    }
}

/**
 * Debounce utility function
 */
function debounce(fn, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn.apply(this, args), delay);
    };
}

// Keyboard shortcuts for verification
document.addEventListener('keydown', (e) => {
    // Only handle if not in an input/textarea
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

    // Ctrl+Enter to submit
    if (e.ctrlKey && e.key === 'Enter') {
        const submitBtn = document.getElementById('submitBtn');
        if (submitBtn && !submitBtn.disabled) {
            showSubmitSummary();
        }
    }

    // Ctrl+Shift+A to pass all
    if (e.ctrlKey && e.shiftKey && e.key === 'A') {
        e.preventDefault();
        passAllItems();
    }
});

// Clear persisted state on successful submit
window.addEventListener('beforeunload', () => {
    // Only clear if form is being submitted
    // Otherwise, state is preserved for page reloads
});

// Export for global access
window.selectDecision = selectDecision;
window.passAllItems = passAllItems;
window.showSubmitSummary = showSubmitSummary;
window.confirmSubmit = confirmSubmit;
