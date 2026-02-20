/**
 * Saints — Saint du jour (calendrier catholique romain)
 * Uses API wrapper instead of raw fetch.
 */
const Saints = {
    _current: null,

    _RANK_CSS: {
        'Solennité': 'solennite',
        'Fête': 'fete',
        'Mémoire obligatoire': 'memoire-obligatoire',
        'Mémoire facultative': 'memoire-facultative',
    },

    _RANK_SHORT: {
        'Solennité': 'Solennité',
        'Fête': 'Fête',
        'Mémoire obligatoire': 'Mém. obligatoire',
        'Mémoire facultative': 'Mém. facultative',
    },

    async init() {
        try {
            const saints = await API.get('/api/saint-du-jour');
            if (saints.length > 0) {
                this._current = saints[0];
                this._renderWidget(saints);
                this._renderHeaderBtn(saints[0]);
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
        const rankCss = this._RANK_CSS[saint.rang_liturgique] || '';
        const rankShort = this._RANK_SHORT[saint.rang_liturgique] || '';
        const rankBadge = rankCss
            ? `<span class="saint-rank saint-rank-${DOMPurify.sanitize(rankCss)}">${DOMPurify.sanitize(rankShort)}</span>`
            : '';

        container.innerHTML = '';
        const widget = document.createElement('div');
        widget.className = 'saint-widget';
        widget.dataset.saintId = saint.id;
        widget.innerHTML = `
            <div class="saint-widget-icon">&#10013;</div>
            <div class="saint-widget-info">
                <div class="saint-widget-label">Saint du jour ${rankBadge}</div>
                <div class="saint-widget-name">${DOMPurify.sanitize(saint.nom)}</div>
                <div class="saint-widget-subtitle">${DOMPurify.sanitize(subtitle)}</div>
            </div>
        `;
        widget.addEventListener('click', () => this.openDetail(saint.id));
        container.appendChild(widget);
        container.hidden = false;
    },

    _renderHeaderBtn(saint) {
        const btn = document.getElementById('saint-header-btn');
        if (!btn) return;
        btn.title = `Saint du jour : ${saint.nom}`;
        btn.setAttribute('aria-label', `Saint du jour : ${saint.nom}`);
        btn.hidden = false;
        btn.addEventListener('click', () => this.openDetail(saint.id));
    },

    async openDetail(id) {
        try {
            const saint = await API.get(`/api/saint/${encodeURIComponent(id)}`);
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
        html += '<div class="saint-header">';
        html += `<h2>${esc(s.nom)}</h2>`;
        if (s.nom_latin) {
            html += `<div class="saint-latin">${esc(s.nom_latin)}</div>`;
        }
        if (s.titres && s.titres.length > 0) {
            html += `<div class="saint-titres">${esc(s.titres.join(' · '))}</div>`;
        }
        if (s.rang_liturgique) {
            const css = this._RANK_CSS[s.rang_liturgique] || '';
            if (css) {
                html += `<div class="saint-rank-badge saint-rank-${esc(css)}">${esc(s.rang_liturgique)}</div>`;
            }
        }
        html += '<div class="saint-meta">';
        html += `<span class="saint-fete">${esc(s.fete)}</span>`;
        if (s.lieu) html += ` · ${esc(s.lieu)}`;
        if (s.naissance && s.mort) {
            html += ` · ${esc(s.naissance)}–${esc(s.mort)}`;
        } else if (s.mort) {
            html += ` · † ${esc(s.mort)}`;
        }
        html += '</div>';
        html += '</div>';

        // Biographie
        if (s.resume) {
            html += '<div class="saint-section">';
            html += '<h3>Biographie</h3>';
            html += `<p class="saint-bio">${esc(s.resume)}</p>`;
            html += '</div>';
        }

        // Citations
        if (s.citations && s.citations.length > 0) {
            html += '<div class="saint-section">';
            html += '<h3>Citations</h3>';
            for (const c of s.citations) {
                html += '<blockquote class="saint-quote">';
                html += `<p>« ${esc(c.texte)} »</p>`;
                if (c.source) html += `<cite>— ${esc(c.source)}</cite>`;
                html += '</blockquote>';
            }
            html += '</div>';
        }

        // Ecrits
        if (s.ecrits && s.ecrits.length > 0) {
            html += '<div class="saint-section">';
            html += '<h3>Écrits</h3>';
            html += '<ul class="saint-ecrits">';
            for (const e of s.ecrits) {
                html += '<li>';
                html += `<strong>${esc(e.titre)}</strong>`;
                if (e.annee) html += ` <span class="saint-annee">(${esc(String(e.annee))})</span>`;
                if (e.description) html += `<br><span class="saint-desc">${esc(e.description)}</span>`;
                html += '</li>';
            }
            html += '</ul>';
            html += '</div>';
        }

        // Themes (clickable → AI search)
        if (s.themes && s.themes.length > 0) {
            html += '<div class="saint-section">';
            html += '<h3>Explorer avec l\'IA</h3>';
            html += '<div class="saint-themes">';
            for (const t of s.themes) {
                html += `<button class="saint-theme saint-theme-btn" data-theme="${esc(t)}" data-saint="${esc(s.nom)}">${esc(t)}</button>`;
            }
            html += '</div>';
            html += '</div>';
        }

        // Sources en ligne
        if (s.sources_en_ligne && s.sources_en_ligne.length > 0) {
            html += '<div class="saint-section saint-links">';
            for (const url of s.sources_en_ligne) {
                try {
                    const parsed = new URL(url);
                    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                        const domain = parsed.hostname.replace('www.', '');
                        html += `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(domain)}</a>`;
                    }
                } catch (_) {}
            }
            html += '</div>';
        }

        // Bouton vers le chatbot
        html += '<div class="saint-ask">';
        html += `<button class="btn btn-primary saint-ask-btn" data-name="${esc(s.nom)}">Plus d'informations avec l'IA</button>`;
        html += '</div>';

        body.innerHTML = html;

        // Event delegation for all clickable actions
        body.addEventListener('click', (e) => {
            const askBtn = e.target.closest('.saint-ask-btn');
            if (askBtn) {
                this._askIA(`Que peux-tu me dire sur ${askBtn.dataset.name} ?`);
                return;
            }
            const themeBtn = e.target.closest('.saint-theme-btn');
            if (themeBtn) {
                const saint = themeBtn.dataset.saint;
                const theme = themeBtn.dataset.theme;
                this._askIA(`Quel est l'enseignement de ${saint} sur le thème « ${theme} » ?`);
            }
        });
    },

    _askIA(question) {
        this.close();
        const input = document.getElementById('chat-input');
        input.value = question;
        input.focus();
        Chat.send();
    },

    close() {
        document.getElementById('saint-modal').hidden = true;
    },
};
