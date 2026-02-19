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

        container.innerHTML = '';
        const widget = document.createElement('div');
        widget.className = 'saint-widget';
        widget.dataset.saintId = saint.id;
        widget.innerHTML = `
            <div class="saint-widget-icon">&#10013;</div>
            <div class="saint-widget-info">
                <div class="saint-widget-label">Saint du jour</div>
                <div class="saint-widget-name">${DOMPurify.sanitize(saint.nom)}</div>
                <div class="saint-widget-subtitle">${DOMPurify.sanitize(subtitle)}</div>
            </div>
        `;
        widget.addEventListener('click', () => this.openDetail(saint.id));
        container.appendChild(widget);
        container.hidden = false;
    },

    async openDetail(id) {
        try {
            const res = await fetch(`/api/saint/${encodeURIComponent(id)}`);
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
        const esc = (str) => DOMPurify.sanitize(str);

        let html = '';

        // Header
        html += `<div class="saint-header">`;
        html += `<h2>${esc(s.nom)}</h2>`;
        if (s.nom_latin) {
            html += `<div class="saint-latin">${esc(s.nom_latin)}</div>`;
        }
        if (s.titres && s.titres.length > 0) {
            html += `<div class="saint-titres">${esc(s.titres.join(' · '))}</div>`;
        }
        html += `<div class="saint-meta">`;
        html += `<span class="saint-fete">${esc(s.fete)}</span>`;
        if (s.lieu) html += ` · ${esc(s.lieu)}`;
        if (s.naissance && s.mort) {
            html += ` · ${esc(s.naissance)}–${esc(s.mort)}`;
        } else if (s.mort) {
            html += ` · † ${esc(s.mort)}`;
        }
        html += `</div>`;
        html += `</div>`;

        // Biographie
        if (s.resume) {
            html += `<div class="saint-section">`;
            html += `<h3>Biographie</h3>`;
            html += `<p class="saint-bio">${esc(s.resume)}</p>`;
            html += `</div>`;
        }

        // Citations
        if (s.citations && s.citations.length > 0) {
            html += `<div class="saint-section">`;
            html += `<h3>Citations</h3>`;
            for (const c of s.citations) {
                html += `<blockquote class="saint-quote">`;
                html += `<p>« ${esc(c.texte)} »</p>`;
                if (c.source) html += `<cite>— ${esc(c.source)}</cite>`;
                html += `</blockquote>`;
            }
            html += `</div>`;
        }

        // Ecrits
        if (s.ecrits && s.ecrits.length > 0) {
            html += `<div class="saint-section">`;
            html += `<h3>Écrits</h3>`;
            html += `<ul class="saint-ecrits">`;
            for (const e of s.ecrits) {
                html += `<li>`;
                html += `<strong>${esc(e.titre)}</strong>`;
                if (e.annee) html += ` <span class="saint-annee">(${esc(String(e.annee))})</span>`;
                if (e.description) html += `<br><span class="saint-desc">${esc(e.description)}</span>`;
                html += `</li>`;
            }
            html += `</ul>`;
            html += `</div>`;
        }

        // Themes
        if (s.themes && s.themes.length > 0) {
            html += `<div class="saint-section">`;
            html += `<div class="saint-themes">`;
            for (const t of s.themes) {
                html += `<span class="saint-theme">${esc(t)}</span>`;
            }
            html += `</div>`;
            html += `</div>`;
        }

        // Sources en ligne
        if (s.sources_en_ligne && s.sources_en_ligne.length > 0) {
            html += `<div class="saint-section saint-links">`;
            for (const url of s.sources_en_ligne) {
                try {
                    const parsed = new URL(url);
                    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                        const domain = parsed.hostname.replace('www.', '');
                        html += `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(domain)}</a>`;
                    }
                } catch (_) { /* skip invalid URLs */ }
            }
            html += `</div>`;
        }

        // Bouton vers le chatbot
        html += `<div class="saint-ask">`;
        html += `<button class="btn btn-primary saint-ask-btn" data-name="${esc(s.nom)}">Plus d'informations avec l'IA</button>`;
        html += `</div>`;

        body.innerHTML = html;

        // Event delegation pour le bouton "ask"
        const askBtn = body.querySelector('.saint-ask-btn');
        if (askBtn) {
            askBtn.addEventListener('click', () => this.askAbout(s.nom));
        }
    },

    askAbout(name) {
        this.close();
        const input = document.getElementById('chat-input');
        input.value = `Que peux-tu me dire sur ${name} ?`;
        input.focus();
        Chat.send();
    },

    close() {
        document.getElementById('saint-modal').hidden = true;
    }
};
