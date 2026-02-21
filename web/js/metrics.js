/**
 * Metrics — Admin dashboard module
 * Charts via Chart.js, tables, KPIs.
 */
const Metrics = {
    _charts: [],
    _days: 30,

    async open(days) {
        if (days) this._days = days;
        _openModal('metrics-modal');
        this._bindPeriod();
        await this._load();
    },

    close() {
        document.getElementById('metrics-modal').hidden = true;
        this._destroyCharts();
    },

    _bindPeriod() {
        const btns = document.querySelectorAll('.metrics-period-btn');
        btns.forEach(btn => {
            btn.addEventListener('click', () => {
                btns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this._days = parseInt(btn.dataset.days, 10);
                this._load();
            });
        });
    },

    async _load() {
        const body = document.getElementById('metrics-body');
        body.innerHTML = '<div class="metrics-loading">Chargement...</div>';
        this._destroyCharts();
        try {
            const data = await API.getMetrics(this._days);
            this._render(data);
        } catch (e) {
            body.innerHTML = `<div class="metrics-loading">Erreur : ${DOMPurify.sanitize(e.message)}</div>`;
        }
    },

    _render(data) {
        const body = document.getElementById('metrics-body');
        body.innerHTML = '';

        this._renderKPIs(body, data.kpis);
        this._renderQuestionsChart(body, data.questions_per_day);

        // Row: clicks + examples
        const row1 = this._row(body);
        this._renderClicksChart(row1, data.click_stats);
        this._renderExamplesChart(row1, data.top_examples);

        // Row: keywords + reconnection
        const row2 = this._row(body);
        this._renderKeywordsChart(row2, data.top_keywords);
        this._renderReconnection(row2, data.reconnection);

        // IP table (full width)
        this._renderGeoTable(body, data.ip_connections);
    },

    _row(parent) {
        const div = document.createElement('div');
        div.className = 'metrics-row';
        parent.appendChild(div);
        return div;
    },

    _card(parent, title) {
        const card = document.createElement('div');
        card.className = 'metrics-card';
        card.innerHTML = `<h3>${DOMPurify.sanitize(title)}</h3>`;
        parent.appendChild(card);
        return card;
    },

    // === KPIs ===
    _renderKPIs(parent, kpis) {
        const grid = document.createElement('div');
        grid.className = 'metrics-kpis';
        const items = [
            { value: kpis.total_views, label: 'Visites' },
            { value: kpis.total_questions, label: 'Questions' },
            { value: kpis.guest_questions, label: 'Guest' },
            { value: kpis.auth_questions, label: 'Connecté' },
            { value: kpis.logins, label: 'Connexions' },
            { value: kpis.registers, label: 'Inscriptions' },
        ];
        for (const item of items) {
            const kpi = document.createElement('div');
            kpi.className = 'metrics-kpi';
            kpi.innerHTML = `<div class="metrics-kpi-value">${item.value}</div><div class="metrics-kpi-label">${item.label}</div>`;
            grid.appendChild(kpi);
        }
        parent.appendChild(grid);
    },

    // === Questions per day (line chart) ===
    _renderQuestionsChart(parent, data) {
        const card = this._card(parent, 'Questions par jour');
        const canvas = document.createElement('canvas');
        canvas.style.maxHeight = '250px';
        card.appendChild(canvas);

        const labels = data.map(d => d.day.slice(5)); // MM-DD
        const chart = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Connecté',
                        data: data.map(d => d.auth),
                        borderColor: '#8b1a2b',
                        backgroundColor: 'rgba(139,26,43,0.1)',
                        fill: true,
                        tension: 0.3,
                    },
                    {
                        label: 'Guest',
                        data: data.map(d => d.guest),
                        borderColor: '#c5961a',
                        backgroundColor: 'rgba(197,150,26,0.1)',
                        fill: true,
                        tension: 0.3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 12, font: { size: 11 } } } },
                scales: {
                    y: { beginAtZero: true, ticks: { stepSize: 1 } },
                    x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
                },
            },
        });
        this._charts.push(chart);
    },

    // === Clicks bar chart ===
    _renderClicksChart(parent, stats) {
        const card = this._card(parent, 'Clics par fonctionnalité');
        const canvas = document.createElement('canvas');
        canvas.style.maxHeight = '220px';
        card.appendChild(canvas);

        const mapping = {
            click_donate: 'Don',
            click_saint: 'Saint du jour',
            click_corpus: 'Corpus',
            click_profile: 'Profil',
            click_share: 'Partage',
            click_example: 'Exemples',
        };
        const labels = [];
        const values = [];
        for (const [key, label] of Object.entries(mapping)) {
            labels.push(label);
            values.push(stats[key] || 0);
        }

        const chart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: ['#8b1a2b', '#c5961a', '#5a4a3e', '#a62038', '#d4a830', '#8a7a6e'],
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
            },
        });
        this._charts.push(chart);
    },

    // === Top examples (horizontal bar) ===
    _renderExamplesChart(parent, examples) {
        const card = this._card(parent, 'Top 5 questions exemples');
        if (!examples.length) {
            card.innerHTML += '<p class="metrics-empty">Pas encore de données</p>';
            return;
        }
        const canvas = document.createElement('canvas');
        canvas.style.maxHeight = '220px';
        card.appendChild(canvas);

        const chart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: examples.map(e => e.label.length > 20 ? e.label.slice(0, 20) + '...' : e.label),
                datasets: [{
                    data: examples.map(e => e.count),
                    backgroundColor: '#c5961a',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: { legend: { display: false } },
                scales: { x: { beginAtZero: true, ticks: { stepSize: 1 } } },
            },
        });
        this._charts.push(chart);
    },

    // === Top keywords (horizontal bar) ===
    _renderKeywordsChart(parent, keywords) {
        const card = this._card(parent, 'Top 10 mots-clés');
        if (!keywords.length) {
            card.innerHTML += '<p class="metrics-empty">Pas encore de données</p>';
            return;
        }
        const canvas = document.createElement('canvas');
        canvas.style.maxHeight = '280px';
        card.appendChild(canvas);

        const chart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: keywords.map(k => k.word),
                datasets: [{
                    data: keywords.map(k => k.count),
                    backgroundColor: '#8b1a2b',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: { legend: { display: false } },
                scales: { x: { beginAtZero: true, ticks: { stepSize: 1 } } },
            },
        });
        this._charts.push(chart);
    },

    // === Reconnection stats ===
    _renderReconnection(parent, stats) {
        const card = this._card(parent, 'Fidélisation');
        const esc = s => DOMPurify.sanitize(String(s));
        card.innerHTML += `
            <table class="metrics-table">
                <tbody>
                    <tr><td>Utilisateurs uniques</td><td><strong>${esc(stats.unique_users)}</strong></td></tr>
                    <tr><td>Utilisateurs fidèles</td><td><strong>${esc(stats.returning_users)}</strong></td></tr>
                    <tr><td>Taux de retour</td><td><strong>${esc(stats.return_rate)}%</strong></td></tr>
                    <tr><td>Délai moyen entre visites</td><td><strong>${esc(stats.avg_days_between)} jours</strong></td></tr>
                </tbody>
            </table>
        `;
    },

    // === IP Geo table ===
    _renderGeoTable(parent, connections) {
        const card = this._card(parent, 'Connexions par IP');
        if (!connections.length) {
            card.innerHTML += '<p class="metrics-empty">Pas encore de données</p>';
            return;
        }
        const esc = s => DOMPurify.sanitize(String(s));
        let html = `
            <table class="metrics-table">
                <thead>
                    <tr><th>IP</th><th>Ville</th><th>Pays</th><th>Visites</th><th>Sessions</th><th>Dernière visite</th></tr>
                </thead>
                <tbody>
        `;
        for (const c of connections) {
            const lastSeen = c.last_seen ? c.last_seen.slice(0, 16).replace('T', ' ') : '';
            html += `<tr>
                <td><code>${esc(c.ip)}</code></td>
                <td>${esc(c.city)}</td>
                <td>${esc(c.country)}</td>
                <td>${esc(c.visits)}</td>
                <td>${esc(c.sessions)}</td>
                <td>${esc(lastSeen)}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        card.innerHTML += html;
    },

    _destroyCharts() {
        for (const c of this._charts) c.destroy();
        this._charts = [];
    },
};
