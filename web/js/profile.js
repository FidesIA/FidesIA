/**
 * Profile — Age group, knowledge level & response length selection
 * DRY binding pattern.
 */
const Profile = {
    ageGroup: 'adulte',
    knowledgeLevel: 'initie',
    responseLength: 'synthetique',

    _optionsConfig: [
        { containerId: 'age-options', prop: 'ageGroup', storageKey: 'fidesia_age' },
        { containerId: 'level-options', prop: 'knowledgeLevel', storageKey: 'fidesia_level' },
        { containerId: 'length-options', prop: 'responseLength', storageKey: 'fidesia_length' },
    ],

    init() {
        // Load from localStorage
        this.ageGroup = localStorage.getItem('fidesia_age') || 'adulte';
        this.knowledgeLevel = localStorage.getItem('fidesia_level') || 'initie';
        this.responseLength = localStorage.getItem('fidesia_length') || 'synthetique';

        // Bind all option groups via event delegation
        for (const cfg of this._optionsConfig) {
            const container = document.getElementById(cfg.containerId);
            container.addEventListener('click', (e) => {
                const btn = e.target.closest('.profile-btn');
                if (!btn) return;
                this[cfg.prop] = btn.dataset.value;
                localStorage.setItem(cfg.storageKey, this[cfg.prop]);
                container.querySelectorAll('.profile-btn').forEach(b => {
                    b.classList.toggle('active', b.dataset.value === this[cfg.prop]);
                });
            });

            // Set initial active states
            container.querySelectorAll('.profile-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.value === this[cfg.prop]);
            });
        }
    },

    open() {
        _openModal('profile-modal');
        API.track('click_profile');
    },

    close() {
        document.getElementById('profile-modal').hidden = true;
    },
};
