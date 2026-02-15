/**
 * Corpus Browser — Browse and search the document corpus
 */
const Corpus = {
    data: null,
    loaded: false,

    init() {
        document.querySelector('#corpus-modal .modal-backdrop').addEventListener('click', () => this.close());
        document.getElementById('corpus-search').addEventListener('input', (e) => this.filter(e.target.value));
    },

    async open() {
        document.getElementById('corpus-modal').hidden = false;
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
            // Sort by year
            docs.sort((a, b) => (a.annee || 0) - (b.annee || 0));

            html += `<div class="corpus-group">`;
            html += `<div class="corpus-group-title">${this._esc(source)} (${docs.length})</div>`;

            for (const doc of docs) {
                const title = doc.titre || doc.fichier || 'Sans titre';
                const year = doc.annee ? `<span class="corpus-year">${doc.annee}</span>` : '';
                const vatLink = doc.url
                    ? `<a class="corpus-link" href="${this._esc(doc.url)}" target="_blank" rel="noopener" title="Vatican.va">vatican.va</a>`
                    : '';
                const pdfPath = doc.fichier ? this._buildPdfPath(doc) : '';
                const pdfClick = pdfPath ? `onclick="Corpus.openPdf('${this._escAttr(pdfPath)}')"` : '';

                html += `<div class="corpus-item" ${pdfClick}>
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

    _buildPdfPath(doc) {
        // The fichier field contains just the filename
        // We need to find which folder it's in
        // For now, just use the filename directly — the backend serves from corpus/
        return doc.fichier || '';
    },

    _esc(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    _escAttr(str) {
        return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }
};
