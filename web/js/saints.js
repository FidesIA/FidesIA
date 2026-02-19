/**
 * Saints — Saint du jour (calendrier catholique romain)
 */
const Saints = {
    _current: null,

    async init() {
        try {
            const res = await fetch('/api/saint-du-jour');
            if (!res.ok) return;
            const saints = await res.json();
            if (saints.length > 0) {
                this._current = saints[0];
                this._renderWidget(saints);
            }
        } catch (e) {
            console.warn('Saints init failed:', e);
        }
    },

    _renderWidget(saints) {
        const container = document.getElementById('saint-du-jour');
        if (!container) return;

        const saint = saints[0];
        const subtitle = saint.titres && saint.titres.length > 0
            ? saint.titres[0]
            : saint.fete;

        container.innerHTML = `
            <div class="saint-widget" onclick="Saints.openDetail('${saint.id}')">
                <div class="saint-widget-icon">&#10013;</div>
                <div class="saint-widget-info">
                    <div class="saint-widget-label">Saint du jour</div>
                    <div class="saint-widget-name">${saint.nom}</div>
                    <div class="saint-widget-subtitle">${subtitle}</div>
                </div>
            </div>
        `;
        container.hidden = false;
    },

    async openDetail(id) {
        try {
            const res = await fetch(`/api/saint/${id}`);
            if (!res.ok) return;
            const saint = await res.json();
            this._renderModal(saint);
            document.getElementById('saint-modal').hidden = false;
        } catch (e) {
            console.warn('Saint detail failed:', e);
        }
    },

    _renderModal(s) {
        const body = document.getElementById('saint-modal-body');

        let html = '';

        // Header
        html += `<div class="saint-header">`;
        html += `<h2>${s.nom}</h2>`;
        if (s.nom_latin) {
            html += `<div class="saint-latin">${s.nom_latin}</div>`;
        }
        if (s.titres && s.titres.length > 0) {
            html += `<div class="saint-titres">${s.titres.join(' · ')}</div>`;
        }
        html += `<div class="saint-meta">`;
        html += `<span class="saint-fete">${s.fete}</span>`;
        if (s.lieu) html += ` · ${s.lieu}`;
        if (s.naissance && s.mort) {
            html += ` · ${s.naissance}–${s.mort}`;
        } else if (s.mort) {
            html += ` · † ${s.mort}`;
        }
        html += `</div>`;
        html += `</div>`;

        // Biographie
        if (s.resume) {
            html += `<div class="saint-section">`;
            html += `<h3>Biographie</h3>`;
            html += `<p class="saint-bio">${s.resume}</p>`;
            html += `</div>`;
        }

        // Citations
        if (s.citations && s.citations.length > 0) {
            html += `<div class="saint-section">`;
            html += `<h3>Citations</h3>`;
            for (const c of s.citations) {
                html += `<blockquote class="saint-quote">`;
                html += `<p>« ${c.texte} »</p>`;
                if (c.source) html += `<cite>— ${c.source}</cite>`;
                html += `</blockquote>`;
            }
            html += `</div>`;
        }

        // Écrits
        if (s.ecrits && s.ecrits.length > 0) {
            html += `<div class="saint-section">`;
            html += `<h3>Écrits</h3>`;
            html += `<ul class="saint-ecrits">`;
            for (const e of s.ecrits) {
                html += `<li>`;
                html += `<strong>${e.titre}</strong>`;
                if (e.annee) html += ` <span class="saint-annee">(${e.annee})</span>`;
                if (e.description) html += `<br><span class="saint-desc">${e.description}</span>`;
                html += `</li>`;
            }
            html += `</ul>`;
            html += `</div>`;
        }

        // Thèmes
        if (s.themes && s.themes.length > 0) {
            html += `<div class="saint-section">`;
            html += `<div class="saint-themes">`;
            for (const t of s.themes) {
                html += `<span class="saint-theme">${t}</span>`;
            }
            html += `</div>`;
            html += `</div>`;
        }

        // Sources
        if (s.sources_en_ligne && s.sources_en_ligne.length > 0) {
            html += `<div class="saint-section saint-links">`;
            for (const url of s.sources_en_ligne) {
                const domain = new URL(url).hostname.replace('www.', '');
                html += `<a href="${url}" target="_blank" rel="noopener">${domain}</a>`;
            }
            html += `</div>`;
        }

        body.innerHTML = html;
    },

    close() {
        document.getElementById('saint-modal').hidden = true;
    }
};
