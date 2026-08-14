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
        kpiCompleted: document.getElementById("kpiCompleted"),
        lastSyncInfo: document.getElementById("lastSyncInfo"),

        // Filter & Search
        searchInput: document.getElementById("searchInput"),
        btnClearSearch: document.getElementById("btnClearSearch"),
        categoryFilter: document.getElementById("categoryFilter"),
        companyFilter: document.getElementById("companyFilter"),
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
            elements.kpiTotal.textContent = data.total_cases.toLocaleString("no-NO");
            elements.kpiActive.textContent = data.active_cases.toLocaleString("no-NO");
            elements.kpiHighRisk.textContent = data.high_risk_cases.toLocaleString("no-NO");
            elements.kpiCompleted.textContent = data.completed_cases.toLocaleString("no-NO");

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
    // Rendering Logic
    // =========================================================================

    function renderCases() {
        elements.resultsCount.textContent = `Viser ${state.cases.length} av ${state.total} saker`;

        if (state.cases.length === 0) {
            const emptyHtml = `
                <div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; background: var(--surface); border-radius: var(--radius-lg); border: 1px solid var(--border);">
                    <i class="ri-search-eye-line" style="font-size: 48px; color: var(--text-subtle); display: block; margin-bottom: 12px;"></i>
                    <h3 style="font-size: 18px; font-weight: 700; color: var(--primary); margin-bottom: 6px;">Ingen saker funnet</h3>
                    <p style="font-size: 14px; color: var(--text-muted); max-width: 400px; margin: 0 auto;">Prøv å justere søkeordet ditt, firmanavn eller nullstill filtervalgene.</p>
                </div>
            `;
            elements.casesContainer.innerHTML = emptyHtml;
            elements.casesTableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 40px;">Ingen saker funnet</td></tr>`;
            return;
        }

        // 1. Render Cards
        elements.casesContainer.innerHTML = state.cases.map(c => createCaseCardHtml(c)).join("");

        // 2. Render Table Rows
        elements.casesTableBody.innerHTML = state.cases.map(c => createTableRowHtml(c)).join("");

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
        const street = addr.street_name ? `${addr.street_name} ${addr.house_number || ''}${addr.house_letter || ''}`.trim() : 'Tønsberg';

        return `
            <div class="case-card" data-id="${c.identifikator}">
                <div>
                    <div class="case-card-header">
                        <span class="saksnummer-badge">${c.saksnummer || 'Uten saksnr'}</span>
                        <span class="case-date"><i class="ri-calendar-line"></i> ${c.dato || 'Ukjent dato'}</span>
                    </div>

                    <h3 class="case-title">${escapeHtml(c.tittel)}</h3>

                    <div class="case-address-row">
                        <i class="ri-map-pin-line"></i>
                        <span>${escapeHtml(street)}</span>
                        ${addr.matrikkel ? `<span class="matrikkel-tag">Gnr ${addr.matrikkel}</span>` : ''}
                    </div>

                    <div class="badges-row">
                        <span class="badge ${riskClass}"><i class="ri-shield-line"></i> ${ev.risk_level || 'Ukjent'} risiko</span>
                        <span class="badge badge-category">${ev.category || 'Byggesak'}</span>
                        ${c.primary_company ? `<span class="badge badge-company" title="Utførende / Firma"><i class="ri-briefcase-line"></i> ${escapeHtml(c.primary_company)}</span>` : ''}
                    </div>
                </div>

                <div class="case-card-footer">
                    <span class="doc-count"><i class="ri-file-text-line"></i> ${c.dokumenter ? c.dokumenter.length : 0} dokumenter</span>
                    <span class="link-details">Vis evaluering <i class="ri-arrow-right-s-line"></i></span>
                </div>
            </div>
        `;
    }

    function createTableRowHtml(c) {
        const ev = c.evaluation || {};
        const addr = c.address_info || {};
        const riskClass = getRiskBadgeClass(ev.risk_level);
        const street = addr.street_name ? `${addr.street_name} ${addr.house_number || ''}`.trim() : '–';

        return `
            <tr>
                <td><strong>${c.saksnummer}</strong></td>
                <td>${c.dato}</td>
                <td>${escapeHtml(street)} ${addr.matrikkel ? `(Gnr ${addr.matrikkel})` : ''}</td>
                <td>${c.primary_company ? `<span class="badge badge-company"><i class="ri-briefcase-line"></i> ${escapeHtml(c.primary_company)}</span>` : '<span style="color: var(--text-subtle);">–</span>'}</td>
                <td style="max-width: 260px; font-weight: 600;">${escapeHtml(c.tittel)}</td>
                <td><span class="badge badge-category">${ev.category || 'Byggesak'}</span></td>
                <td><span class="badge ${riskClass}">${ev.risk_level || 'Lav'}</span></td>
                <td>${c.dokumenter ? c.dokumenter.length : 0}</td>
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
                <p>Laster inn saksdetaljer og evalueringsrapport...</p>
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
        const street = addr.street_name ? `${addr.street_name} ${addr.house_number || ''}${addr.house_letter || ''}`.trim() : 'Tønsberg';

        elements.drawerContent.innerHTML = `
            <div class="drawer-header">
                <div class="drawer-meta-bar">
                    <span class="saksnummer-badge">${c.saksnummer}</span>
                    <span class="badge ${riskClass}">${ev.risk_level} risiko</span>
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

            <!-- Evalueringsrapport -->
            <div class="eval-scorecard">
                <div class="eval-scorecard-title">
                    <i class="ri-sparkling-fill" style="color: #f59e0b;"></i>
                    <span>Faglig Evalueringsrapport</span>
                </div>

                <div class="eval-stats-row">
                    <div class="eval-stat-box">
                        <span class="eval-stat-num">${ev.risk_score || 0}/100</span>
                        <span class="eval-stat-label">Risikoscore</span>
                    </div>
                    <div class="eval-stat-box">
                        <span class="eval-stat-num">${ev.complexity_score || 0}/10</span>
                        <span class="eval-stat-label">Kompleksitet (${ev.complexity})</span>
                    </div>
                    <div class="eval-stat-box">
                        <span class="eval-stat-num">${ev.days_in_process !== null ? ev.days_in_process + ' dager' : '–'}</span>
                        <span class="eval-stat-label">Behandlingstid</span>
                    </div>
                </div>

                <p class="eval-summary-text">${escapeHtml(ev.summary || '')}</p>

                ${ev.risk_factors && ev.risk_factors.length > 0 ? `
                    <div class="eval-factors-list">
                        <strong style="font-size: 12px; text-transform: uppercase; color: #991b1b;">Identifiserte risikofaktorer:</strong>
                        ${ev.risk_factors.map(f => `<div class="factor-item"><i class="ri-alert-fill"></i> <span>${escapeHtml(f)}</span></div>`).join("")}
                    </div>
                ` : ''}

                ${ev.recommendation ? `
                    <div class="eval-recommendation-box" style="margin-top: 14px;">
                        <strong><i class="ri-lightbulb-line"></i> Saksbehandleranbefaling:</strong>
                        <p style="margin-top: 4px;">${escapeHtml(ev.recommendation)}</p>
                    </div>
                ` : ''}
            </div>

            <!-- Dokumenter & Journalposter -->
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

            const companyHtml = p.primary_company ? `<div style="font-size: 11px; color: #4338ca; font-weight: 600; margin-bottom: 4px;"><i class="ri-briefcase-line"></i> ${escapeHtml(p.primary_company)}</div>` : '';

            const popupHtml = `
                <div style="font-family: var(--font-sans); min-width: 220px;">
                    <span style="font-size: 11px; font-weight: 700; color: #64748b;">${p.saksnummer}</span>
                    <h4 style="font-size: 14px; font-weight: 700; color: #0f2b48; margin: 4px 0 6px 0;">${escapeHtml(p.tittel)}</h4>
                    ${companyHtml}
                    <div style="font-size: 12px; color: #475569; margin-bottom: 8px;">
                        <strong>Kategori:</strong> ${p.category}<br>
                        <strong>Risiko:</strong> ${p.risk_level} (${p.risk_score}/100)
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
    });

    elements.btnViewTable.addEventListener("click", () => {
        state.viewMode = "table";
        elements.btnViewTable.classList.add("active");
        elements.btnViewCards.classList.remove("active");
        elements.casesContainer.classList.add("hidden");
        elements.tableContainer.classList.remove("hidden");
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
