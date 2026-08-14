/**
 * Byggeval – Frontend Application Logic
 * Integrert mot FastAPI backend og Tønsberg Innsyn API
 */

document.addEventListener("DOMContentLoaded", () => {
    // App State
    const state = {
        cases: [],
        companies: [],
        total: 0,
        limit: 24,
        offset: 0,
        currentPage: 1,
        searchQuery: "",
        selectedCategory: "all",
        selectedCompany: "all",
        selectedStage: "all",
        selectedDeadline: "all",
        selectedRisk: "all",
        selectedSort: "dato_desc",
        viewMode: "cards", // 'cards' | 'table'
        activeTab: "explorer", // 'explorer' | 'map' | 'analytics'
        map: null,
        markersLayer: null,
        charts: {},
        syncInterval: null
    };

    // DOM Elements
    const elements = {
        // KPIs
        kpiTotal: document.getElementById("kpiTotal"),
        kpiActive: document.getElementById("kpiActive"),
        kpiHighRisk: document.getElementById("kpiHighRisk"),
        kpiOverdue: document.getElementById("kpiOverdue"),
        kpiCompleted: document.getElementById("kpiCompleted"),
        lastSyncInfo: document.getElementById("lastSyncInfo"),

        // Filter & Search
        searchInput: document.getElementById("searchInput"),
        btnClearSearch: document.getElementById("btnClearSearch"),
        categoryFilter: document.getElementById("categoryFilter"),
        companyFilter: document.getElementById("companyFilter"),
        stageFilter: document.getElementById("stageFilter"),
        deadlineFilter: document.getElementById("deadlineFilter"),
        riskFilter: document.getElementById("riskFilter"),
        sortFilter: document.getElementById("sortFilter"),

        // Containers
        casesContainer: document.getElementById("casesContainer"),
        tableContainer: document.getElementById("tableContainer"),
        casesTableBody: document.getElementById("casesTableBody"),
        resultsCount: document.getElementById("resultsCount"),

        // View Toggles
        btnViewCards: document.getElementById("btnViewCards"),
        btnViewTable: document.getElementById("btnViewTable"),

        // Pagination
        btnPrevPage: document.getElementById("btnPrevPage"),
        btnNextPage: document.getElementById("btnNextPage"),
        paginationInfo: document.getElementById("paginationInfo"),

        // Tabs & Panes
        tabButtons: document.querySelectorAll(".tab-button"),
        tabPanes: document.querySelectorAll(".tab-pane"),

        // Drawer
        detailModalOverlay: document.getElementById("detailModalOverlay"),
        drawerContent: document.getElementById("drawerContent"),
        btnDrawerClose: document.getElementById("btnDrawerClose"),

        // Sync Modal
        btnSyncModal: document.getElementById("btnSyncModal"),
        syncModalOverlay: document.getElementById("syncModalOverlay"),
        btnSyncModalClose: document.getElementById("btnSyncModalClose"),
        btnSyncCancel: document.getElementById("btnSyncCancel"),
        btnStartSync: document.getElementById("btnStartSync"),
        syncPagesInput: document.getElementById("syncPagesInput"),
        syncSearchInput: document.getElementById("syncSearchInput"),
        syncProgressBox: document.getElementById("syncProgressBox"),
        syncProgressText: document.getElementById("syncProgressText"),

        // Map stats
        mapStatsBox: document.getElementById("mapStatsBox")
    };

    // =========================================================================
    // API Data Fetching
    // =========================================================================

    async function fetchStats() {
        try {
            const res = await fetch("/api/stats");
            const data = await res.json();

            // Update KPIs
            elements.kpiTotal.textContent = (data.total_cases || 0).toLocaleString("no-NO");
            elements.kpiActive.textContent = (data.active_cases || 0).toLocaleString("no-NO");
            elements.kpiHighRisk.textContent = (data.high_risk_cases || 0).toLocaleString("no-NO");
            if (elements.kpiOverdue) {
                elements.kpiOverdue.textContent = (data.overdue_cases || 0).toLocaleString("no-NO");
            }
            elements.kpiCompleted.textContent = (data.completed_cases || 0).toLocaleString("no-NO");

            // Last sync text
            if (data.last_sync) {
                const syncDate = new Date(data.last_sync.timestamp);
                elements.lastSyncInfo.innerHTML = `<i class="ri-history-line"></i> Sist synkronisert: ${syncDate.toLocaleDateString("no-NO")} kl. ${syncDate.toLocaleTimeString("no-NO", {hour: '2-digit', minute:'2-digit'})}`;
            } else {
                elements.lastSyncInfo.innerHTML = `<i class="ri-history-line"></i> Database klar`;
            }

            // Update Charts if on analytics tab
            if (state.activeTab === "analytics") {
                renderCharts(data);
            }
        } catch (err) {
            console.error("Feil ved henting av statistikk:", err);
        }
    }

    async function fetchCompanies() {
        try {
            const res = await fetch("/api/companies?limit=150");
            const data = await res.json();
            state.companies = data.companies || [];

            // Populate company filter select
            const currentSelected = state.selectedCompany;
            elements.companyFilter.innerHTML = `<option value="all">Alle firmaer / utførende (${state.companies.length})</option>` +
                state.companies.map(c => `<option value="${escapeHtml(c.name)}" ${currentSelected === c.name ? 'selected' : ''}>${escapeHtml(c.name)} (${c.count})</option>`).join("");
        } catch (err) {
            console.error("Feil ved henting av firmaer:", err);
        }
    }

    async function fetchCases() {
        elements.casesContainer.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">
                <div class="spinner" style="margin: 0 auto 12px auto;"></div>
                <span>Henter byggesaker...</span>
            </div>
        `;

        try {
            const params = new URLSearchParams({
                limit: state.limit,
                offset: (state.currentPage - 1) * state.limit,
                sort_by: state.selectedSort
            });

            if (state.searchQuery) params.append("search", state.searchQuery);
            if (state.selectedCategory !== "all") params.append("category", state.selectedCategory);
            if (state.selectedCompany !== "all") params.append("company", state.selectedCompany);
            if (state.selectedStage !== "all") params.append("stage", state.selectedStage);
            if (state.selectedDeadline !== "all") params.append("deadline_status", state.selectedDeadline);
            if (state.selectedRisk !== "all") params.append("risk_level", state.selectedRisk);

            const res = await fetch(`/api/cases?${params.toString()}`);
            const data = await res.json();

            state.cases = data.cases || [];
            state.total = data.total || 0;

            renderCases();
            updatePagination();
        } catch (err) {
            console.error("Feil ved henting av saker:", err);
            elements.casesContainer.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--danger);">
                    <i class="ri-error-warning-line" style="font-size: 32px; display: block; margin-bottom: 8px;"></i>
                    Kunne ikke laste byggesaker. Vennligst sjekk serverforbindelsen.
                </div>
            `;
        }
    }

    async function fetchMapPoints() {
        try {
            const res = await fetch("/api/map");
            const points = await res.json();
            renderMap(points);
        } catch (err) {
            console.error("Feil ved henting av kartpunkter:", err);
        }
    }

    // =========================================================================
    // Decision, Stage & Deadline Helpers
    // =========================================================================

    function getOfficialDecisionBadge(c) {
        if (!c) return '';
        if (c.has_official_decision) {
            const dtype = c.official_decision_type || 'Innvilget vedtak';
            const docInfo = c.decision_document_title ? `Vedtaksdokument: "${c.decision_document_title}" (${c.decision_date || c.dato})` : '';

            if (dtype.includes('Avslått') || dtype.includes('Avslag')) {
                return `<span class="badge badge-official-rejected" title="${escapeHtml(docInfo)}"><i class="ri-close-circle-fill"></i> Offisielt vedtak: ${escapeHtml(dtype)}</span>`;
            }
            if (dtype.includes('Ferdigattest')) {
                return `<span class="badge badge-official-approved" title="${escapeHtml(docInfo)}"><i class="ri-award-fill"></i> Offisielt vedtak: Ferdigattest</span>`;
            }
            if (dtype.includes('Igangsetting')) {
                return `<span class="badge badge-official-approved" title="${escapeHtml(docInfo)}"><i class="ri-hammer-fill"></i> Offisielt vedtak: Igangsetting gitt</span>`;
            }
            return `<span class="badge badge-official-approved" title="${escapeHtml(docInfo)}"><i class="ri-checkbox-circle-fill"></i> Offisielt vedtak: ${escapeHtml(dtype)}</span>`;
        }

        return `<span class="badge badge-official-pending" title="Ingen formelt vedtaksdokument registrert ennå"><i class="ri-loader-2-line"></i> Kommune: ${escapeHtml(c.official_status || 'Under behandling')}</span>`;
    }

    function getStageInfo(stageRaw) {
        const stage = stageRaw || "Under saksbehandling";
        const s = stage.toLowerCase();

        if (s.includes("vedtatt") || s.includes("tillatelse gitt") || s.includes("godkjent")) {
            return {
                slug: "vedtatt",
                label: "Vedtatt / Tillatelse gitt",
                icon: "ri-checkbox-circle-fill",
                desc: "Søknaden er formelt behandlet og tillatelse er innvilget av Tønsberg kommune.",
                stepIndex: 3
            };
        }
        if (s.includes("igangsetting")) {
            return {
                slug: "igangsetting",
                label: "Igangsettingstillatelse",
                icon: "ri-hammer-fill",
                desc: "Igangsettingstillatelse er gitt. Byggearbeider kan nå igangsettes på eiendommen.",
                stepIndex: 4
            };
        }
        if (s.includes("ferdigattest")) {
            return {
                slug: "ferdigattest",
                label: "Ferdigattest",
                icon: "ri-award-fill",
                desc: "Tiltaket er ferdigstilt og ferdigattest / midlertidig brukstillatelse er registrert.",
                stepIndex: 4
            };
        }
        if (s.includes("forhåndskonferanse")) {
            return {
                slug: "forhandskonferanse",
                label: "Forhåndskonferanse",
                icon: "ri-chat-voice-fill",
                desc: "Saken gjelder forhåndskonferanse for veiledning og planavklaring før formell søknad.",
                stepIndex: 1
            };
        }
        if (s.includes("avventer") || s.includes("supplering") || s.includes("mangel")) {
            return {
                slug: "avventer",
                label: "Avventer dokumentasjon",
                icon: "ri-time-fill",
                desc: "Kommunen har etterspurt tilleggsopplysninger før vedtak kan fattes.",
                stepIndex: 2
            };
        }
        if (s.includes("ulovlighet") || s.includes("stans")) {
            return {
                slug: "ulovlighet",
                label: "Ulovlighet / Tilsyn",
                icon: "ri-alert-fill",
                desc: "Kommunens tilsynsavdeling følger opp ulovlige byggearbeider eller stansingsvarsel.",
                stepIndex: 2
            };
        }
        if (s.includes("ferdig") || s.includes("avsluttet")) {
            return {
                slug: "ferdigbehandlet",
                label: "Ferdigbehandlet",
                icon: "ri-archive-fill",
                desc: "Saken er fullført og arkivert.",
                stepIndex: 4
            };
        }

        // Standard: Under saksbehandling
        return {
            slug: "under-behandling",
            label: "Under saksbehandling",
            icon: "ri-loader-4-fill",
            desc: "Saken er registrert og under aktiv saksbehandling hos bygningsmyndighetene.",
            stepIndex: 2
        };
    }

    function getDeadlineBadge(ev) {
        if (!ev) return '';
        const status = ev.deadline_status || 'God tid';
        const days = ev.days_remaining;
        const weeks = ev.statutory_deadline_weeks || 12;
        const basis = ev.legal_basis || 'pbl § 21-7';
        const completeDate = ev.complete_application_date ? `Komplett søknad: ${ev.complete_application_date}` : '';

        if (ev.is_deadline_paused) {
            return `<span class="badge badge-deadline-urgent" title="${escapeHtml(ev.deadline_pause_reason || 'Frist stanset i påvente av tilleggsopplysninger')}"><i class="ri-pause-circle-line"></i> Frist stanset (Mangelbrev)</span>`;
        }
        if (status === 'Vedtatt / Avsluttet') {
            return `<span class="badge badge-deadline-completed" title="${escapeHtml(basis)} &bull; ${completeDate}"><i class="ri-check-line"></i> Fullført (${ev.days_in_process || 0}d)</span>`;
        }
        if (status === 'Fristoverskridelse') {
            const overdueDays = Math.abs(days || 0);
            return `<span class="badge badge-deadline-overdue" title="${escapeHtml(basis)} &bull; ${completeDate} &bull; Fristoverskridelse etter ${weeks} uker"><i class="ri-alarm-warning-fill"></i> Overskredet (-${overdueDays}d)</span>`;
        }
        if (status === 'Nærmer seg frist') {
            return `<span class="badge badge-deadline-urgent" title="${escapeHtml(basis)} &bull; ${completeDate} &bull; Lovpålagt frist: ${ev.deadline_date || ''}"><i class="ri-timer-fill"></i> ${days} dager gjenstår</span>`;
        }
        return `<span class="badge badge-deadline-ok" title="${escapeHtml(basis)} &bull; ${completeDate} &bull; Lovpålagt frist: ${ev.deadline_date || ''}"><i class="ri-time-line"></i> ${days || 0} dager igjen (${weeks}u)</span>`;
    }

    // =========================================================================
    // Rendering Logic
    // =========================================================================

    function renderCases() {
        elements.resultsCount.textContent = `Viser ${state.cases.length} av ${state.total} saker`;

        if (state.cases.length === 0) {
            const emptyHtml = `
                <div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; background: var(--surface); border-radius: var(--radius-lg); border: 1px solid var(--border);">
                    <i class="ri-search-eye-line" style="font-size: 48px; color: var(--text-subtle); display: block; margin-bottom: 12px;"></i>
                    <h3 style="font-size: 18px; font-weight: 700; color: var(--primary); margin-bottom: 6px;">Ingen saker funnet</h3>
                    <p style="font-size: 14px; color: var(--text-muted); max-width: 400px; margin: 0 auto;">Prøv å justere søkeordet ditt, friststatus eller nullstill filtervalgene.</p>
                </div>
            `;
            elements.casesContainer.innerHTML = emptyHtml;
            elements.casesTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 40px;">Ingen saker funnet</td></tr>`;
            return;
        }

        // Render kun aktiv visningsmodus for å spare CPU og minne
        if (state.viewMode === "cards") {
            elements.casesContainer.innerHTML = state.cases.map(c => createCaseCardHtml(c)).join("");
            elements.casesTableBody.innerHTML = "";
        } else {
            elements.casesTableBody.innerHTML = state.cases.map(c => createTableRowHtml(c)).join("");
            elements.casesContainer.innerHTML = "";
        }

        // Add Click Handlers for opening drawer
        document.querySelectorAll(".case-card, .btn-table-detail").forEach(el => {
            el.addEventListener("click", () => {
                const id = el.getAttribute("data-id");
                openCaseDrawer(id);
            });
        });
    }

    function createCaseCardHtml(c) {
        const ev = c.evaluation || {};
        const addr = c.address_info || {};
        const riskClass = getRiskBadgeClass(ev.risk_level);
        const stageInfo = getStageInfo(ev.stage);
        const officialBadgeHtml = getOfficialDecisionBadge(c);
        const deadlineBadgeHtml = getDeadlineBadge(ev);
        const street = addr.street_name ? `${addr.street_name} ${addr.house_number || ''}${addr.house_letter || ''}`.trim() : 'Tønsberg';

        // Kommunens faktiske status på kortet
        const municipalStatusLabel = c.has_official_decision ? c.official_decision_type : (c.official_status || stageInfo.label);

        return `
            <div class="case-card" data-id="${c.identifikator}">
                <div>
                    <!-- Topplinje med Saksnummer og Kommunens Status-Pill -->
                    <div class="case-card-header">
                        <span class="saksnummer-badge">${c.saksnummer || 'Uten saksnr'}</span>
                        <span class="status-pill status-${stageInfo.slug}">
                            <span class="status-dot ${stageInfo.slug === 'under-behandling' ? 'status-dot-pulse' : ''}"></span>
                            <i class="${stageInfo.icon}"></i>
                            ${escapeHtml(municipalStatusLabel)}
                        </span>
                    </div>

                    <h3 class="case-title">${escapeHtml(c.tittel)}</h3>

                    <!-- Tydelig statusbanner fra kommunen -->
                    <div class="case-status-banner status-${stageInfo.slug}">
                        <i class="${stageInfo.icon}"></i>
                        <span><strong>Kommunens status:</strong> ${escapeHtml(municipalStatusLabel)}</span>
                    </div>

                    <div class="case-address-row">
                        <i class="ri-map-pin-line"></i>
                        <span>${escapeHtml(street)}</span>
                        ${addr.matrikkel ? `<span class="matrikkel-tag">Gnr ${addr.matrikkel}</span>` : ''}
                    </div>

                    <div class="badges-row">
                        ${officialBadgeHtml}
                        <span class="badge ${riskClass}" title="Byggeval automatisert risikovurdering"><i class="ri-sparkling-fill"></i> ${ev.risk_level || 'Ukjent'} risiko</span>
                        ${deadlineBadgeHtml}
                        <span class="badge badge-category">${ev.category || 'Byggesak'}</span>
                        ${c.primary_company ? `<span class="badge badge-company" title="Utførende / Firma"><i class="ri-briefcase-line"></i> ${escapeHtml(c.primary_company)}</span>` : ''}
                    </div>
                </div>

                <div class="case-card-footer">
                    <span class="doc-count"><i class="ri-file-text-line"></i> ${c.dokumenter ? c.dokumenter.length : 0} dok. &bull; <i class="ri-calendar-line"></i> ${c.dato || ''}</span>
                    <span class="link-details">Vis vedtak & analyse <i class="ri-arrow-right-s-line"></i></span>
                </div>
            </div>
        `;
    }

    function createTableRowHtml(c) {
        const ev = c.evaluation || {};
        const addr = c.address_info || {};
        const riskClass = getRiskBadgeClass(ev.risk_level);
        const officialBadgeHtml = getOfficialDecisionBadge(c);
        const deadlineBadgeHtml = getDeadlineBadge(ev);
        const street = addr.street_name ? `${addr.street_name} ${addr.house_number || ''}`.trim() : '–';

        return `
            <tr>
                <td><strong>${c.saksnummer}</strong></td>
                <td>${officialBadgeHtml}</td>
                <td>${deadlineBadgeHtml}</td>
                <td>${c.dato}</td>
                <td>${escapeHtml(street)} ${addr.matrikkel ? `(Gnr ${addr.matrikkel})` : ''}</td>
                <td>${c.primary_company ? `<span class="badge badge-company"><i class="ri-briefcase-line"></i> ${escapeHtml(c.primary_company)}</span>` : '<span style="color: var(--text-subtle);">–</span>'}</td>
                <td style="max-width: 220px; font-weight: 600;">${escapeHtml(c.tittel)}</td>
                <td><span class="badge badge-category">${ev.category || 'Byggesak'}</span></td>
                <td><span class="badge ${riskClass}"><i class="ri-sparkling-fill"></i> ${ev.risk_level || 'Lav'}</span></td>
                <td>
                    <button class="btn btn-secondary btn-sm btn-table-detail" data-id="${c.identifikator}">
                        Åpne
                    </button>
                </td>
            </tr>
        `;
    }

    function updatePagination() {
        const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
        elements.paginationInfo.textContent = `Side ${state.currentPage} av ${totalPages}`;
        elements.btnPrevPage.disabled = state.currentPage <= 1;
        elements.btnNextPage.disabled = state.currentPage >= totalPages;
    }

    // =========================================================================
    // Case Detail Drawer
    // =========================================================================

    async function openCaseDrawer(identifikator) {
        elements.detailModalOverlay.classList.remove("hidden");
        elements.drawerContent.innerHTML = `
            <div style="text-align: center; padding: 80px 20px;">
                <div class="spinner" style="margin: 0 auto 16px auto;"></div>
                <p>Laster inn kommunale vedtak og evalueringsanalyse...</p>
            </div>
        `;

        try {
            const res = await fetch(`/api/cases/${identifikator}`);
            if (!res.ok) throw new Error("Kunne ikke hente saksdetaljer");
            const c = await res.json();
            renderDrawerContent(c);
        } catch (err) {
            elements.drawerContent.innerHTML = `
                <div style="text-align: center; padding: 40px; color: var(--danger);">
                    <h3>Kunne ikke laste saken</h3>
                    <p>${err.message}</p>
                </div>
            `;
        }
    }

    function renderDrawerContent(c) {
        const ev = c.evaluation || {};
        const addr = c.address_info || {};
        const riskClass = getRiskBadgeClass(ev.risk_level);
        const stageInfo = getStageInfo(ev.stage);
        const street = addr.street_name ? `${addr.street_name} ${addr.house_number || ''}${addr.house_letter || ''}`.trim() : 'Tønsberg';

        // Stepper status
        const step1Class = stageInfo.stepIndex >= 1 ? (stageInfo.stepIndex === 1 ? 'active' : 'completed') : '';
        const step2Class = stageInfo.stepIndex >= 2 ? (stageInfo.stepIndex === 2 ? 'active' : 'completed') : '';
        const step3Class = stageInfo.stepIndex >= 3 ? (stageInfo.stepIndex === 3 ? 'active' : 'completed') : '';
        const step4Class = stageInfo.stepIndex >= 4 ? (stageInfo.stepIndex === 4 ? 'active' : 'completed') : '';

        // Deadline calculations for drawer
        const daysInProc = ev.days_in_process || 0;
        const totalDeadlineDays = ev.statutory_deadline_days || 84;
        const progressPct = Math.min(100, Math.round((daysInProc / totalDeadlineDays) * 100));
        const daysRem = ev.days_remaining;
        
        let deadlineColor = '#10b981';
        if (ev.deadline_status === 'Fristoverskridelse') {
            deadlineColor = '#ef4444';
        } else if (ev.deadline_status === 'Nærmer seg frist' || ev.is_deadline_paused) {
            deadlineColor = '#f59e0b';
        } else if (ev.deadline_status === 'Vedtatt / Avsluttet') {
            deadlineColor = '#3b82f6';
        }

        // Decision styling
        let decisionBoxClass = 'decision-pending';
        let decisionIcon = 'ri-time-line';
        if (c.has_official_decision) {
            if (c.official_decision_type.includes('Avslått') || c.official_decision_type.includes('Avslag')) {
                decisionBoxClass = 'decision-rejected';
                decisionIcon = 'ri-close-circle-fill';
            } else {
                decisionBoxClass = 'decision-permit';
                decisionIcon = 'ri-checkbox-circle-fill';
            }
        }

        // Kommunens faktiske status
        const municipalStatusLabel = c.has_official_decision ? c.official_decision_type : (c.official_status || stageInfo.label);

        elements.drawerContent.innerHTML = `
            <div class="drawer-header">
                <div class="drawer-meta-bar">
                    <span class="saksnummer-badge">${c.saksnummer}</span>
                    <span class="status-pill status-${stageInfo.slug}">
                        <span class="status-dot"></span>
                        <i class="${stageInfo.icon}"></i>
                        ${escapeHtml(municipalStatusLabel)}
                    </span>
                    <span class="badge badge-category">${ev.category}</span>
                </div>

                <h2 class="drawer-title">${escapeHtml(c.tittel)}</h2>

                <div class="drawer-address">
                    <i class="ri-map-pin-2-fill" style="color: var(--accent);"></i>
                    <span>${escapeHtml(street)}</span>
                    ${addr.matrikkel ? `<span class="matrikkel-tag">Gnr ${addr.matrikkel}</span>` : ''}
                    <span style="margin-left: auto; color: var(--text-muted); font-size: 13px;">Registrert: ${c.dato}</span>
                </div>

                ${c.primary_company ? `
                    <div style="background: #eef2ff; border: 1px solid #c7d2fe; border-radius: var(--radius-md); padding: 10px 14px; display: flex; align-items: center; gap: 8px; margin-bottom: 16px; font-size: 13px; color: #3730a3;">
                        <i class="ri-briefcase-4-line" style="font-size: 16px;"></i>
                        <span><strong>Utførende foretak / søker:</strong> ${escapeHtml(c.primary_company)}</span>
                    </div>
                ` : ''}

                <a href="${c.innsyn_url}" target="_blank" rel="noopener noreferrer" class="drawer-innsyn-btn">
                    <i class="ri-external-link-line"></i>
                    <span>Åpne sak i Tønsberg kommunes postliste</span>
                </a>
            </div>

            <!-- SEKSJON 1: OFFISIELL KOMMUNAL STATUS & VEDTAK -->
            <div class="official-decision-box ${decisionBoxClass}">
                <div class="official-decision-header">
                    <span class="official-badge-tag"><i class="ri-government-line"></i> Kommunens offisielle status</span>
                    <span style="font-size: 12px; font-weight: 600; color: #475569;">Offisiell status: ${escapeHtml(c.official_status || 'Under behandling')}</span>
                </div>

                <div class="official-decision-title">
                    <i class="${decisionIcon}"></i>
                    <span>${c.has_official_decision ? escapeHtml(c.official_decision_type) : 'Ingen formelt vedtak fattet ennå (Under saksbehandling)'}</span>
                </div>

                ${c.has_official_decision && c.decision_document_title ? `
                    <div class="official-doc-item">
                        <div><strong><i class="ri-file-shield-2-line"></i> Journalført vedtaksdokument fra kommunen:</strong></div>
                        <div style="font-weight: 600; margin: 2px 0;">${escapeHtml(c.decision_document_title)}</div>
                        ${c.decision_date ? `<div style="color: var(--text-muted); font-size: 11px;">Dato for vedtak: ${c.decision_date}</div>` : ''}
                    </div>
                ` : `
                    <p style="font-size: 12px; color: var(--text-muted); margin: 6px 0 0 0;">
                        Kommunen har foreløpig ikke fattet eller journalført et formelt enkeltvedtak (rammetillatelse, ett-trinnstillatelse eller ferdigattest) i saken.
                    </p>
                `}
            </div>

            <!-- SEKSJON 2: LOVPÅLAGT SAKSBEHANDLINGSFRIST -->
            <div class="drawer-deadline-box">
                <div class="deadline-header-row">
                    <strong style="font-size: 14px; color: var(--primary); display: flex; align-items: center; gap: 6px;">
                        <i class="ri-timer-line" style="color: ${deadlineColor}; font-size: 18px;"></i>
                        <span>Lovpålagt Saksbehandlingsfrist (Løper fra komplett søknad)</span>
                    </strong>
                    ${getDeadlineBadge(ev)}
                </div>

                ${ev.is_deadline_paused ? `
                    <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: var(--radius-md); padding: 10px 14px; margin-bottom: 12px; font-size: 12px; color: #92400e; display: flex; align-items: center; gap: 8px;">
                        <i class="ri-pause-circle-fill" style="font-size: 16px; color: #d97706;"></i>
                        <span><strong>Fristen er stanset:</strong> ${escapeHtml(ev.deadline_pause_reason || 'Kommunen har etterspurt tilleggsopplysninger.')}</span>
                    </div>
                ` : ''}

                <div class="deadline-stats-grid">
                    <div class="deadline-stat-card">
                        <span class="deadline-stat-value">${ev.statutory_deadline_weeks || 12} uker</span>
                        <span class="deadline-stat-label">Lovpålagt frist</span>
                    </div>
                    <div class="deadline-stat-card">
                        <span class="deadline-stat-value">${ev.complete_application_date || c.dato || '–'}</span>
                        <span class="deadline-stat-label">Komplett søknad</span>
                    </div>
                    <div class="deadline-stat-card">
                        <span class="deadline-stat-value">${ev.deadline_date || '–'}</span>
                        <span class="deadline-stat-label">Fristdato</span>
                    </div>
                    <div class="deadline-stat-card">
                        <span class="deadline-stat-value" style="color: ${deadlineColor};">${daysRem !== null ? (daysRem >= 0 ? daysRem + ' dager' : '-' + Math.abs(daysRem) + ' dager') : '–'}</span>
                        <span class="deadline-stat-label">Resttid / Avvik</span>
                    </div>
                </div>

                <!-- Fremdriftslinje for frist -->
                <div class="deadline-progress-container">
                    <div class="deadline-progress-bar" style="width: ${progressPct}%; background-color: ${deadlineColor};"></div>
                </div>

                <div style="font-size: 12px; color: var(--text-muted); line-height: 1.4;">
                    <i class="ri-scales-3-line" style="margin-right: 4px; color: var(--accent);"></i>
                    <strong>Hjemmel:</strong> ${escapeHtml(ev.legal_basis || 'Plan- og bygningsloven § 21-7 (Fristen løper fra komplett søknad)')}
                </div>
            </div>

            <!-- SEKSJON 3: BYGGEVAL AUTOMATISERT FAGLIG EVALUERING & ANBEFALING -->
            <div class="eval-scorecard">
                <div class="eval-scorecard-title">
                    <span style="display: flex; align-items: center; gap: 8px;">
                        <i class="ri-sparkling-fill" style="color: #f59e0b;"></i>
                        <span>Byggeval Evalueringsanalyse</span>
                    </span>
                    <span class="badge badge-byggeval-eval"><i class="ri-cpu-line"></i> Evaluert anbefaling</span>
                </div>

                <!-- Tydelig ansvarsfraskrivelse / skille mellom offisielt vedtak og analyse -->
                <div class="eval-disclaimer-callout">
                    <strong><i class="ri-information-line"></i> Evaluert faglig anbefaling (Ikke bindende enkeltvedtak)</strong>
                    <span>Dette er en automatisert analyse og faglig veiledning generert av Byggeval basert på sakens dokumenter og Plan- og bygningsloven. Erstattet ikke kommunens formelle enkeltvedtak.</span>
                </div>

                <div class="eval-stats-row">
                    <div class="eval-stat-box">
                        <span class="eval-stat-num">${ev.risk_score || 0}/100</span>
                        <span class="eval-stat-label">Byggeval Risikoscore</span>
                    </div>
                    <div class="eval-stat-box">
                        <span class="eval-stat-num">${ev.complexity_score || 0}/10</span>
                        <span class="eval-stat-label">Kompleksitet (${ev.complexity})</span>
                    </div>
                    <div class="eval-stat-box">
                        <span class="eval-stat-num">${daysInProc} dager</span>
                        <span class="eval-stat-label">Behandlingstid</span>
                    </div>
                </div>

                <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 14px; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-size: 13px; color: var(--text-muted);"><strong>Vurdert saksstadium:</strong> ${escapeHtml(ev.stage || 'Under saksbehandling')}</span>
                    <span class="status-pill status-${stageInfo.slug}"><span class="status-dot"></span>${escapeHtml(stageInfo.label)}</span>
                </div>

                <p class="eval-summary-text">${escapeHtml(ev.summary || '')}</p>

                ${ev.risk_factors && ev.risk_factors.length > 0 ? `
                    <div class="eval-factors-list">
                        <strong style="font-size: 12px; text-transform: uppercase; color: #991b1b;">Identifiserte risikofaktorer fra Byggeval:</strong>
                        ${ev.risk_factors.map(f => `<div class="factor-item"><i class="ri-alert-fill"></i> <span>${escapeHtml(f)}</span></div>`).join("")}
                    </div>
                ` : ''}

                ${ev.recommendation ? `
                    <div class="eval-recommendation-box" style="margin-top: 14px;">
                        <strong><i class="ri-lightbulb-line"></i> Veiledende saksbehandleranbefaling fra Byggeval:</strong>
                        <p style="margin-top: 4px;">${escapeHtml(ev.recommendation)}</p>
                    </div>
                ` : ''}
            </div>

            <!-- SEKSJON 4: BEHANDLINGSLØP -->
            <div class="drawer-status-box">
                <div class="drawer-status-header">
                    <strong style="font-size: 14px; color: var(--primary); display: flex; align-items: center; gap: 6px;">
                        <i class="ri-progress-3-line" style="color: var(--accent);"></i> Behandlingsløp & Fremdrift
                    </strong>
                    <span class="status-pill status-${stageInfo.slug}">
                        <span class="status-dot"></span>
                        <i class="${stageInfo.icon}"></i>
                        ${escapeHtml(stageInfo.label)}
                    </span>
                </div>
                <p class="drawer-status-desc">${escapeHtml(stageInfo.desc)}</p>

                <!-- 4-Trinns Visuell Fremdriftslinje -->
                <div class="progress-stepper">
                    <div class="step-item ${step1Class}">
                        <div class="step-circle"><i class="ri-file-text-line"></i></div>
                        <span class="step-label">1. Mottatt / Forhåndskonferanse</span>
                    </div>
                    <div class="step-item ${step2Class}">
                        <div class="step-circle"><i class="ri-time-line"></i></div>
                        <span class="step-label">2. Saksbehandling & Varsling</span>
                    </div>
                    <div class="step-item ${step3Class}">
                        <div class="step-circle"><i class="ri-checkbox-circle-line"></i></div>
                        <span class="step-label">3. Vedtak & Rammetillatelse</span>
                    </div>
                    <div class="step-item ${step4Class}">
                        <div class="step-circle"><i class="ri-building-line"></i></div>
                        <span class="step-label">4. Igangsetting & Ferdigattest</span>
                    </div>
                </div>
            </div>

            <!-- SEKSJON 5: DOKUMENTER & JOURNALPOSTER -->
            <div class="docs-section">
                <h3 class="section-heading">
                    <i class="ri-folder-open-line"></i>
                    <span>Journalposter og dokumenter (${c.dokumenter ? c.dokumenter.length : 0})</span>
                </h3>

                <div class="docs-timeline">
                    ${c.dokumenter && c.dokumenter.length > 0 ? c.dokumenter.map(d => `
                        <div class="doc-timeline-item">
                            <div>
                                <h4 class="doc-title">${escapeHtml(d.tittel)}</h4>
                                <div class="doc-meta">
                                    <span class="doc-friendly-id">${d.friendly_id || 'Dokument'}</span>
                                    <span><i class="ri-calendar-line"></i> ${d.dato || c.dato}</span>
                                    ${d.fra && d.fra.length > 0 ? `<span><i class="ri-user-shared-line"></i> Fra: ${escapeHtml(d.fra.join(", "))}</span>` : ''}
                                </div>
                            </div>
                            <span class="badge ${d.synlighet === 1 ? 'badge-risk-lav' : 'badge-risk-moderat'}">
                                ${d.synlighet === 1 ? 'Offentlig' : 'Skjermet'}
                            </span>
                        </div>
                    `).join("") : '<p style="color: var(--text-muted);">Ingen tilknyttede journalposter registrert i innsyn.</p>'}
                </div>
            </div>
        `;
    }

    // =========================================================================
    // Leaflet Interactive Map
    // =========================================================================

    function initMap() {
        if (state.map) return;

        state.map = L.map("leafletMap").setView([59.2675, 10.4075], 12);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> bidragsytere',
            maxZoom: 18
        }).addTo(state.map);

        state.markersLayer = L.layerGroup().addTo(state.map);
    }

    function renderMap(points) {
        initMap();
        state.markersLayer.clearLayers();

        elements.mapStatsBox.innerHTML = `<strong>${points.length} byggesaker</strong> plassert i Tønsberg kommune.`;

        points.forEach(p => {
            const color = getPinColor(p.risk_level);
            const iconHtml = `<div class="custom-map-pin" style="background-color: ${color};"><i class="ri-building-line"></i></div>`;
            
            const customIcon = L.divIcon({
                html: iconHtml,
                className: "custom-leaflet-div-icon",
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            });

            const marker = L.marker([p.latitude, p.longitude], { icon: customIcon });

            const stageInfo = getStageInfo(p.stage);
            const companyHtml = p.primary_company ? `<div style="font-size: 11px; color: #4338ca; font-weight: 600; margin-bottom: 4px;"><i class="ri-briefcase-line"></i> ${escapeHtml(p.primary_company)}</div>` : '';

            const popupHtml = `
                <div style="font-family: var(--font-sans); min-width: 220px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span style="font-size: 11px; font-weight: 700; color: #64748b;">${p.saksnummer}</span>
                        <span class="status-pill status-${stageInfo.slug}" style="font-size: 10px; padding: 2px 6px;"><span class="status-dot"></span>${escapeHtml(stageInfo.label)}</span>
                    </div>
                    <h4 style="font-size: 14px; font-weight: 700; color: #0f2b48; margin: 4px 0 6px 0;">${escapeHtml(p.tittel)}</h4>
                    ${companyHtml}
                    <div style="font-size: 12px; color: #475569; margin-bottom: 8px;">
                        <strong>Kategori:</strong> ${p.category}<br>
                        <strong>Byggeval Risiko:</strong> ${p.risk_level} (${p.risk_score}/100)
                    </div>
                    <button class="btn btn-primary btn-sm btn-map-popup" data-id="${p.identifikator}" style="width: 100%;">
                        Åpne sak
                    </button>
                </div>
            `;

            marker.bindPopup(popupHtml);
            state.markersLayer.addLayer(marker);
        });

        // Event delegation for popup buttons
        state.map.on("popupopen", () => {
            document.querySelectorAll(".btn-map-popup").forEach(btn => {
                btn.addEventListener("click", () => {
                    const id = btn.getAttribute("data-id");
                    openCaseDrawer(id);
                });
            });
        });
    }

    // =========================================================================
    // Chart.js Analytics
    // =========================================================================

    function renderCharts(data) {
        // 1. Category Breakdown
        const catCanvas = document.getElementById("chartCategory");
        if (catCanvas && data.category_breakdown) {
            if (state.charts.category) state.charts.category.destroy();

            const labels = data.category_breakdown.map(c => c.category);
            const counts = data.category_breakdown.map(c => c.count);

            state.charts.category = new Chart(catCanvas, {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [{
                        label: "Antall saker",
                        data: counts,
                        backgroundColor: "#2563eb",
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { color: "#f1f5f9" } },
                        x: { grid: { display: false } }
                    }
                }
            });
        }

        // 2. Risk Donut
        const riskCanvas = document.getElementById("chartRisk");
        if (riskCanvas && data.risk_breakdown) {
            if (state.charts.risk) state.charts.risk.destroy();

            const labels = data.risk_breakdown.map(r => r.risk_level);
            const counts = data.risk_breakdown.map(r => r.count);
            const colors = labels.map(l => {
                if (l === "Lav") return "#10b981";
                if (l === "Moderat") return "#f59e0b";
                if (l === "Høy") return "#ea580c";
                return "#dc2626";
            });

            state.charts.risk = new Chart(riskCanvas, {
                type: "doughnut",
                data: {
                    labels: labels,
                    datasets: [{
                        data: counts,
                        backgroundColor: colors,
                        borderWidth: 2,
                        borderColor: "#ffffff"
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom" }
                    },
                    cutout: "65%"
                }
            });
        }

        // 3. Stage Pipeline
        const stageCanvas = document.getElementById("chartStage");
        if (stageCanvas && data.stage_breakdown) {
            if (state.charts.stage) state.charts.stage.destroy();

            const labels = data.stage_breakdown.map(s => s.stage);
            const counts = data.stage_breakdown.map(s => s.count);

            state.charts.stage = new Chart(stageCanvas, {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [{
                        label: "Saker i stadium",
                        data: counts,
                        backgroundColor: "#0ea5e9",
                        borderRadius: 6
                    }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { beginAtZero: true, grid: { color: "#f1f5f9" } },
                        y: { grid: { display: false } }
                    }
                }
            });
        }

        // 4. Top Companies Chart
        const compCanvas = document.getElementById("chartCompanies");
        if (compCanvas && data.top_companies) {
            if (state.charts.companies) state.charts.companies.destroy();

            const labels = data.top_companies.map(c => c.name);
            const counts = data.top_companies.map(c => c.count);

            state.charts.companies = new Chart(compCanvas, {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [{
                        label: "Antall byggesaker",
                        data: counts,
                        backgroundColor: "#6366f1",
                        borderRadius: 6
                    }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: "#f1f5f9" } },
                        y: { grid: { display: false } }
                    }
                }
            });
        }
    }

    // =========================================================================
    // Live Sync Functionality
    // =========================================================================

    async function handleStartSync() {
        const pages = parseInt(elements.syncPagesInput.value, 10) || 2;
        const search = elements.syncSearchInput.value.trim() || null;

        elements.syncProgressBox.classList.remove("hidden");
        elements.btnStartSync.disabled = true;

        try {
            const res = await fetch("/api/sync", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pages, search })
            });
            const data = await res.json();

            // Start polling sync status
            state.syncInterval = setInterval(async () => {
                const statusRes = await fetch("/api/sync/status");
                const statusData = await statusRes.json();

                if (statusData.is_syncing) {
                    elements.syncProgressText.textContent = statusData.progress || "Synkroniserer med Tønsberg kommune...";
                } else {
                    clearInterval(state.syncInterval);
                    elements.syncProgressText.textContent = statusData.last_result || "Synkronisering fullført!";
                    setTimeout(() => {
                        elements.syncModalOverlay.classList.add("hidden");
                        elements.syncProgressBox.classList.add("hidden");
                        elements.btnStartSync.disabled = false;
                        fetchStats();
                        fetchCompanies();
                        fetchCases();
                        if (state.activeTab === "map") fetchMapPoints();
                    }, 1200);
                }
            }, 1000);
        } catch (err) {
            elements.syncProgressText.textContent = "Feil under synkronisering.";
            elements.btnStartSync.disabled = false;
        }
    }

    // =========================================================================
    // Event Listeners & Interactions
    // =========================================================================

    // Search with Debounce
    let searchTimeout = null;
    elements.searchInput.addEventListener("input", (e) => {
        const val = e.target.value;
        elements.btnClearSearch.classList.toggle("hidden", !val);
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.searchQuery = val.trim();
            state.currentPage = 1;
            fetchCases();
        }, 300);
    });

    elements.btnClearSearch.addEventListener("click", () => {
        elements.searchInput.value = "";
        elements.btnClearSearch.classList.add("hidden");
        state.searchQuery = "";
        state.currentPage = 1;
        fetchCases();
    });

    // Filters
    elements.categoryFilter.addEventListener("change", (e) => {
        state.selectedCategory = e.target.value;
        state.currentPage = 1;
        fetchCases();
    });

    elements.companyFilter.addEventListener("change", (e) => {
        state.selectedCompany = e.target.value;
        state.currentPage = 1;
        fetchCases();
    });

    elements.stageFilter.addEventListener("change", (e) => {
        state.selectedStage = e.target.value;
        state.currentPage = 1;
        fetchCases();
    });

    if (elements.deadlineFilter) {
        elements.deadlineFilter.addEventListener("change", (e) => {
            state.selectedDeadline = e.target.value;
            state.currentPage = 1;
            fetchCases();
        });
    }

    elements.riskFilter.addEventListener("change", (e) => {
        state.selectedRisk = e.target.value;
        state.currentPage = 1;
        fetchCases();
    });

    elements.sortFilter.addEventListener("change", (e) => {
        state.selectedSort = e.target.value;
        fetchCases();
    });

    // Pagination
    elements.btnPrevPage.addEventListener("click", () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            fetchCases();
            window.scrollTo({ top: 400, behavior: "smooth" });
        }
    });

    elements.btnNextPage.addEventListener("click", () => {
        const totalPages = Math.ceil(state.total / state.limit);
        if (state.currentPage < totalPages) {
            state.currentPage++;
            fetchCases();
            window.scrollTo({ top: 400, behavior: "smooth" });
        }
    });

    // View Toggles (Cards vs Table)
    elements.btnViewCards.addEventListener("click", () => {
        state.viewMode = "cards";
        elements.btnViewCards.classList.add("active");
        elements.btnViewTable.classList.remove("active");
        elements.casesContainer.classList.remove("hidden");
        elements.tableContainer.classList.add("hidden");
        renderCases();
    });

    elements.btnViewTable.addEventListener("click", () => {
        state.viewMode = "table";
        elements.btnViewTable.classList.add("active");
        elements.btnViewCards.classList.remove("active");
        elements.casesContainer.classList.add("hidden");
        elements.tableContainer.classList.remove("hidden");
        renderCases();
    });

    // Main Tab Navigation
    elements.tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            state.activeTab = targetTab;

            elements.tabButtons.forEach(b => b.classList.remove("active"));
            elements.tabPanes.forEach(p => p.classList.add("hidden"));

            btn.classList.add("active");
            document.getElementById(`pane-${targetTab}`).classList.remove("hidden");

            if (targetTab === "map") {
                setTimeout(() => {
                    fetchMapPoints();
                    if (state.map) state.map.invalidateSize();
                }, 100);
            } else if (targetTab === "analytics") {
                fetchStats();
            }
        });
    });

    // Drawer Close
    elements.btnDrawerClose.addEventListener("click", () => {
        elements.detailModalOverlay.classList.add("hidden");
    });

    elements.detailModalOverlay.addEventListener("click", (e) => {
        if (e.target === elements.detailModalOverlay) {
            elements.detailModalOverlay.classList.add("hidden");
        }
    });

    // Sync Modal Open/Close
    elements.btnSyncModal.addEventListener("click", () => {
        elements.syncModalOverlay.classList.remove("hidden");
    });

    elements.btnSyncModalClose.addEventListener("click", () => {
        elements.syncModalOverlay.classList.add("hidden");
    });

    elements.btnSyncCancel.addEventListener("click", () => {
        elements.syncModalOverlay.classList.add("hidden");
    });

    elements.btnStartSync.addEventListener("click", handleStartSync);

    // =========================================================================
    // Helpers
    // =========================================================================

    function getRiskBadgeClass(risk) {
        if (!risk) return "badge-risk-lav";
        const r = risk.toLowerCase();
        if (r.includes("kritisk")) return "badge-risk-kritisk";
        if (r.includes("høy")) return "badge-risk-høy";
        if (r.includes("moderat")) return "badge-risk-moderat";
        return "badge-risk-lav";
    }

    function getPinColor(risk) {
        if (!risk) return "#10b981";
        const r = risk.toLowerCase();
        if (r.includes("kritisk")) return "#dc2626";
        if (r.includes("høy")) return "#ea580c";
        if (r.includes("moderat")) return "#f59e0b";
        return "#10b981";
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Initial Load
    fetchStats();
    fetchCompanies();
    fetchCases();
});
