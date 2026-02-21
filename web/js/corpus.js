/**
 * Corpus Browser — Browse and search the document corpus
 * Debounced filter, cached _esc via textContent.
 */
const Corpus = {
    data: null,
    loaded: false,
    _filterTimer: null,

    init() {
        // Debounced search (300ms)
        document.getElementById('corpus-search').addEventListener('input', (e) => {
            clearTimeout(this._filterTimer);
            this._filterTimer = setTimeout(() => this.filter(e.target.value), 300);
        });

        // Event delegation for corpus items and links
        document.getElementById('corpus-list').addEventListener('click', (e) => {
            const link = e.target.closest('.corpus-link');
            if (link) return; // Let the <a> handle it natively

            const item = e.target.closest('.corpus-item');
            if (item && item.dataset.pdf) {
                this.openPdf(item.dataset.pdf);
            }
        });
    },

    async open() {
        _openModal('corpus-modal');
        if (!this.loaded) await this.load();
    },

    close() {
        document.getElementById('corpus-modal').hidden = true;
    },

    async load() {
        try {
            this.data = await API.corpus();
            this.loaded = true;
            this.render(this.data);
        } catch (e) {
            document.getElementById('corpus-list').innerHTML =
                '<p style="color:var(--text-muted)">Erreur de chargement du corpus.</p>';
        }
    },

    render(items) {
        const list = document.getElementById('corpus-list');
        if (!items || items.length === 0) {
            list.innerHTML = '<p style="color:var(--text-muted)">Aucun document trouvé.</p>';
            return;
        }

        // Group by source
        const groups = {};
        for (const item of items) {
            const source = item.source || 'Autre';
            if (!groups[source]) groups[source] = [];
            groups[source].push(item);
        }

        let html = '';
        for (const [source, docs] of Object.entries(groups)) {
            docs.sort((a, b) => (a.annee || 0) - (b.annee || 0));

            html += '<div class="corpus-group">';
            html += `<div class="corpus-group-title">${this._esc(source)} (${docs.length})</div>`;

            for (const doc of docs) {
                const title = doc.titre || doc.fichier || 'Sans titre';
                const year = doc.annee ? `<span class="corpus-year">${doc.annee}</span>` : '';
                const vatLink = doc.url && this._isValidUrl(doc.url)
                    ? `<a class="corpus-link" href="${this._escAttr(doc.url)}" target="_blank" rel="noopener" title="Vatican.va">vatican.va</a>`
                    : '';
                const pdfPath = doc.fichier || '';

                html += `<div class="corpus-item" ${pdfPath ? `data-pdf="${this._escAttr(pdfPath)}"` : ''}>
                    ${year}
                    <span class="source-name">${this._esc(title)}</span>
                    ${vatLink}
                </div>`;
            }
            html += '</div>';
        }

        list.innerHTML = html;
    },

    filter(query) {
        if (!this.data) return;
        const q = query.toLowerCase().trim();
        if (!q) {
            this.render(this.data);
            return;
        }
        const filtered = this.data.filter(item => {
            const text = `${item.titre || ''} ${item.source || ''} ${item.categorie || ''} ${item.fichier || ''} ${item.annee || ''}`.toLowerCase();
            return text.includes(q);
        });
        this.render(filtered);
    },

    openPdf(path) {
        window.open(`/corpus/file/${encodeURIComponent(path)}`, '_blank');
    },

    _isValidUrl(str) {
        try {
            const url = new URL(str);
            return url.protocol === 'http:' || url.protocol === 'https:';
        } catch (_) {
            return false;
        }
    },

    _esc(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    _escAttr(str) {
        return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },
};
