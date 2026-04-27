/* Journal Entries — Rapidfire keyboard + form layer.
   Loaded only when .je-page is in the DOM. Every handler guards on that
   so the script becomes inert after the user navigates away. */
(function () {
    "use strict";

    // HTMX re-executes <script> tags inside swapped content (defer is ignored
    // for HTMX-injected scripts), so without this guard navigating away and
    // back would stack duplicate document-level listeners.
    if (window.__jeRapidfireMounted) return;
    window.__jeRapidfireMounted = true;

    const FIELD_ORDER = ["account", "amount", "entity"];
    const FMT = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    const CLEAR_TARGET_ROWS = 10;

    function jeMounted() { return !!document.querySelector(".je-page"); }
    function fmt(n) {
        return (Math.round(Number(n) * 100) / 100).toLocaleString("en-US", FMT);
    }
    function signed(n) {
        if (n === 0) return "0.00";
        return (n > 0 ? "+" : "-") + fmt(Math.abs(n));
    }
    function parseAmt(v) {
        if (v == null) return 0;
        const n = parseFloat(String(v).replace(/,/g, ""));
        return isNaN(n) ? 0 : n;
    }
    function setText(id, txt) {
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
    }
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
    }
    function cssEscape(s) {
        return (window.CSS && window.CSS.escape) ? window.CSS.escape(s) : String(s).replace(/"/g, '\\"');
    }

    // Delta totals + balanced state
    let lastTotals = { d: NaN, c: NaN, balanced: null };
    function recalcTotals() {
        const form = document.getElementById("journal-entry-form");
        if (!form) return;
        let d = 0, c = 0;
        form.querySelectorAll('input[name^="debits-"][name$="-amount"]').forEach(i => { d += parseAmt(i.value); });
        form.querySelectorAll('input[name^="credits-"][name$="-amount"]').forEach(i => { c += parseAmt(i.value); });
        const balanced = Math.abs(d - c) < 0.005 && d > 0;
        if (d === lastTotals.d && c === lastTotals.c && balanced === lastTotals.balanced) return;
        lastTotals = { d, c, balanced };

        setText("je-total-debit", fmt(d));
        setText("je-total-credit", fmt(c));
        setText("je-total-delta", signed(d - c));
        setText("je-debit-total-inline", "$" + fmt(d));
        setText("je-credit-total-inline", "$" + fmt(c));

        const dBox = document.getElementById("je-box-debit");
        const cBox = document.getElementById("je-box-credit");
        const xBox = document.getElementById("je-box-delta");
        if (dBox) dBox.classList.toggle("balanced", balanced);
        if (cBox) cBox.classList.toggle("balanced", balanced);
        if (xBox) {
            xBox.classList.toggle("balanced", balanced);
            xBox.classList.toggle("off", !balanced);
        }
    }

    // Tab order — row-major across debit / credit columns
    function getOrderedFormInputs() {
        const inputs = Array.from(document.querySelectorAll(
            '#debit-lines input[data-kind], #credit-lines input[data-kind]'
        ));
        return inputs.sort((a, b) => {
            const ia = +a.dataset.idx, ib = +b.dataset.idx;
            if (ia !== ib) return ia - ib;
            if (a.dataset.kind !== b.dataset.kind) return a.dataset.kind === "debit" ? -1 : 1;
            return FIELD_ORDER.indexOf(a.dataset.f) - FIELD_ORDER.indexOf(b.dataset.f);
        });
    }

    // Add line — clones the last row in the column and increments the Django
    // formset management TOTAL_FORMS counter so the new row is part of POST.
    function addLine(kind, opts) {
        const wrap = document.getElementById(kind + "-lines");
        if (!wrap) return;
        const rows = wrap.querySelectorAll(".je-line");
        const last = rows[rows.length - 1];
        if (!last) return;
        const newIdx = rows.length;
        const prefix = kind === "debit" ? "debits" : "credits";

        const totalForms = document.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);
        if (totalForms) totalForms.value = String(parseInt(totalForms.value, 10) + 1);

        const clone = last.cloneNode(true);
        clone.querySelectorAll("input").forEach(input => {
            const oldIdx = input.dataset.idx;
            input.value = "";
            input.classList.remove("is-invalid");
            if (oldIdx != null) input.dataset.idx = String(newIdx);
            if (input.name) input.name = input.name.replace(/-\d+-/, `-${newIdx}-`);
            if (input.id) input.id = input.id.replace(/-\d+-/, `-${newIdx}-`);
        });
        const idxLabel = clone.querySelector(".num-idx");
        if (idxLabel) idxLabel.textContent = String(newIdx + 1).padStart(2, "0") + ".";
        clone.querySelectorAll(".invalid-feedback").forEach(n => n.remove());
        wrap.appendChild(clone);
        if (!(opts && opts.skipFocus)) {
            const firstInput = clone.querySelector('input[data-f="account"]');
            if (firstInput) firstInput.focus();
        }
        recalcTotals();
    }

    function clearEntry() {
        ["debit", "credit"].forEach(kind => {
            const wrap = document.getElementById(kind + "-lines");
            if (!wrap) return;
            const prefix = kind === "debit" ? "debits" : "credits";
            const totalForms = document.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);
            const rows = Array.from(wrap.querySelectorAll(".je-line"));
            rows.forEach((row, i) => {
                if (i >= CLEAR_TARGET_ROWS) {
                    row.remove();
                    if (totalForms) totalForms.value = String(parseInt(totalForms.value, 10) - 1);
                    return;
                }
                row.querySelectorAll("input").forEach(input => {
                    input.value = "";
                    input.classList.remove("is-invalid");
                });
                row.querySelectorAll(".invalid-feedback").forEach(n => n.remove());
            });
            while (wrap.querySelectorAll(".je-line").length < CLEAR_TARGET_ROWS) {
                addLine(kind, { skipFocus: true });
            }
        });
        recalcTotals();
    }

    function submitEntry() {
        const form = document.getElementById("journal-entry-form");
        const btn = document.getElementById("je-submit-btn");
        if (form && btn) form.requestSubmit(btn);
    }

    // Chip pickers — drives a real <select multiple> so form POST is identical
    // to the Bootstrap version.
    function closeAllChipMenus() {
        document.querySelectorAll(".je-chip-select.open").forEach(x => x.classList.remove("open"));
    }
    function toggleChipMenu(host) {
        const wasOpen = host.classList.contains("open");
        closeAllChipMenus();
        if (!wasOpen) host.classList.add("open");
    }
    function chipDisplayHtml(label, value) {
        return `<span class="je-chip" data-val="${escapeHtml(value)}">${escapeHtml(label)}<span class="x" data-val="${escapeHtml(value)}">×</span></span>`;
    }
    function refreshChip(host) {
        const select = host.querySelector("select.je-chip-source");
        const display = host.querySelector(".je-chip-display");
        const menu = host.querySelector(".je-chip-menu");
        if (!select || !display || !menu) return;
        const placeholder = host.dataset.placeholder || "Any";
        const selected = Array.from(select.selectedOptions);
        if (selected.length === 0) {
            display.innerHTML = `<span class="je-chip-placeholder">${escapeHtml(placeholder)}</span>`;
        } else {
            display.innerHTML = selected.map(o => chipDisplayHtml(o.textContent.trim(), o.value)).join("");
        }
        menu.querySelectorAll(".je-chip-menu-item").forEach(item => {
            const val = item.dataset.val;
            const opt = select.querySelector(`option[value="${cssEscape(val)}"]`);
            item.classList.toggle("checked", !!(opt && opt.selected));
        });
    }
    function chipMenuHtml(select) {
        return Array.from(select.options).map(opt =>
            `<div class="je-chip-menu-item${opt.selected ? " checked" : ""}" data-val="${escapeHtml(opt.value)}"><span class="box"></span><span>${escapeHtml(opt.textContent.trim())}</span></div>`
        ).join("");
    }
    function buildChipMenus() {
        document.querySelectorAll(".je-chip-select").forEach(host => {
            const select = host.querySelector("select.je-chip-source");
            const menu = host.querySelector(".je-chip-menu");
            if (!select || !menu) return;
            menu.innerHTML = chipMenuHtml(select);
            refreshChip(host);
        });
    }

    // Selection (j / k / Enter)
    function getTransactionRows() {
        return Array.from(document.querySelectorAll('#transactions-table tbody tr[data-transaction-id]'));
    }
    function highlightRow(row) {
        if (!row) return;
        document.querySelectorAll('#transactions-table tbody tr.selected').forEach(r => r.classList.remove("selected"));
        row.classList.add("selected");
        row.scrollIntoView({ block: "nearest" });
    }
    function moveSelection(delta) {
        const rows = getTransactionRows();
        if (!rows.length) return;
        const cur = rows.findIndex(r => r.classList.contains("selected"));
        const ni = cur < 0
            ? (delta > 0 ? 0 : rows.length - 1)
            : Math.max(0, Math.min(rows.length - 1, cur + delta));
        highlightRow(rows[ni]);
    }
    function bindSelectedRow() {
        const sel = document.querySelector('#transactions-table tbody tr.selected');
        if (sel) sel.click();
    }

    // Help overlay
    function toggleHelp(force) {
        const o = document.getElementById("je-kb-overlay");
        if (!o) return;
        if (force === true) o.classList.add("show");
        else if (force === false) o.classList.remove("show");
        else o.classList.toggle("show");
    }

    // Event wiring
    document.addEventListener("input", e => {
        if (!jeMounted()) return;
        const el = e.target;
        if (!(el instanceof HTMLInputElement)) return;
        if (el.dataset.f === "amount") recalcTotals();
    });

    document.addEventListener("click", e => {
        if (!jeMounted()) return;
        const target = e.target;
        if (!(target instanceof Element)) return;

        // Sync .selected class when a transaction row is clicked, so the
        // keyboard navigator (which reads .selected) stays consistent with
        // Alpine's selectedRowId / rowIndex.
        const txRow = target.closest('#transactions-table tbody tr[data-transaction-id]');
        if (txRow) highlightRow(txRow);

        const chipHost = target.closest(".je-chip-select");
        if (chipHost) {
            const removeBtn = target.closest(".je-chip .x");
            if (removeBtn) {
                e.stopPropagation();
                const val = removeBtn.dataset.val;
                const select = chipHost.querySelector("select.je-chip-source");
                if (select) {
                    const opt = select.querySelector(`option[value="${cssEscape(val)}"]`);
                    if (opt) opt.selected = false;
                    refreshChip(chipHost);
                }
                return;
            }
            const menuItem = target.closest(".je-chip-menu-item");
            if (menuItem) {
                e.stopPropagation();
                const val = menuItem.dataset.val;
                const select = chipHost.querySelector("select.je-chip-source");
                if (select) {
                    const opt = select.querySelector(`option[value="${cssEscape(val)}"]`);
                    if (opt) opt.selected = !opt.selected;
                    refreshChip(chipHost);
                }
                return;
            }
            if (!target.closest(".je-chip-menu")) {
                toggleChipMenu(chipHost);
            }
            return;
        }
        if (!target.closest(".je-chip-select")) closeAllChipMenus();

        const addBtn = target.closest(".je-row-add");
        if (addBtn) {
            e.preventDefault();
            addLine(addBtn.dataset.kind);
            return;
        }
        if (target.closest(".je-help-cue")) {
            e.preventDefault();
            toggleHelp();
            return;
        }
        if (target.id === "je-kb-overlay" || target.closest("#je-kb-overlay [data-close]")) {
            toggleHelp(false);
            return;
        }
        const dropdown = target.closest(".je-nav-dropdown");
        if (dropdown && target.closest(".je-nav-dropdown-toggle")) {
            e.preventDefault();
            document.querySelectorAll(".je-nav-dropdown.open").forEach(n => {
                if (n !== dropdown) n.classList.remove("open");
            });
            dropdown.classList.toggle("open");
            return;
        }
        if (!target.closest(".je-nav-dropdown")) {
            document.querySelectorAll(".je-nav-dropdown.open").forEach(n => n.classList.remove("open"));
        }
    });

    document.addEventListener("keydown", e => {
        if (!jeMounted()) return;
        const active = document.activeElement;
        const inField = active && ["INPUT", "SELECT", "TEXTAREA"].includes(active.tagName);

        if (e.key === "Tab" && active && active.tagName === "INPUT" && active.dataset.kind) {
            const inputs = getOrderedFormInputs();
            const cur = inputs.indexOf(active);
            if (cur >= 0) {
                if (e.shiftKey) {
                    if (cur > 0) { e.preventDefault(); inputs[cur - 1].focus(); }
                } else {
                    e.preventDefault();
                    if (cur < inputs.length - 1) inputs[cur + 1].focus();
                    else document.getElementById("je-submit-btn")?.focus();
                }
            }
            return;
        }

        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            submitEntry();
            return;
        }

        if (e.key === "Escape") {
            const overlay = document.getElementById("je-kb-overlay");
            if (overlay && overlay.classList.contains("show")) { toggleHelp(false); return; }
            if (document.querySelector(".je-chip-select.open")) { closeAllChipMenus(); return; }
            if (inField) { active.blur(); return; }
            clearEntry();
            return;
        }

        if (e.key === "?") { e.preventDefault(); toggleHelp(); return; }

        if (inField) return;

        if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); moveSelection(1); return; }
        if (e.key === "k" || e.key === "ArrowUp")   { e.preventDefault(); moveSelection(-1); return; }
        if (e.key === "Enter")                      { e.preventDefault(); bindSelectedRow(); return; }
        if (e.key === "p") {
            e.preventDefault();
            const fillBtn = document.querySelector(".je-ps-fill:not(:disabled)");
            if (fillBtn) fillBtn.click();
            return;
        }
        if (e.key === "n") { e.preventDefault(); addLine("debit"); return; }
        if (e.key === "N") { e.preventDefault(); addLine("credit"); return; }
    });

    // Preserve transactions-table scroll position across the post-submit
    // swap that replaces #table-and-form (and with it the scroll container).
    let savedTxScroll = null;
    document.body.addEventListener("htmx:beforeSwap", e => {
        if (!jeMounted()) return;
        if (e.target && e.target.id === "table-and-form") {
            const scroller = document.getElementById("transactions-table");
            if (scroller) savedTxScroll = scroller.scrollTop;
        }
    });

    document.body.addEventListener("htmx:afterSwap", e => {
        if (!jeMounted()) return;
        // Filter form is outside any swap target, so chip menus only need
        // rebuilding when a swap actually replaces a chip-select host.
        if (e.target && e.target.querySelector && e.target.querySelector(".je-chip-select")) {
            buildChipMenus();
        }
        recalcTotals();
    });

    // Scroll restoration runs on afterSettle (not afterSwap) so the new
    // table-and-form has been laid out — otherwise scrollTop gets clamped to
    // a pre-layout scrollHeight that's smaller than the saved value.
    document.body.addEventListener("htmx:afterSettle", e => {
        if (!jeMounted()) return;
        if (savedTxScroll == null) return;
        if (!e.target || e.target.id !== "table-and-form") return;
        const want = savedTxScroll;
        savedTxScroll = null;
        const scroller = document.getElementById("transactions-table");
        if (scroller) scroller.scrollTop = want;
    });

    function init() {
        if (!jeMounted()) return;
        buildChipMenus();
        recalcTotals();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
