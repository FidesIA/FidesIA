/**
 * Profile — Age group, knowledge level & response length selection
 */
const Profile = {
    ageGroup: 'adulte',
    knowledgeLevel: 'initie',
    responseLength: 'synthetique',

    init() {
        // Load from localStorage
        this.ageGroup = localStorage.getItem('fidesia_age') || 'adulte';
        this.knowledgeLevel = localStorage.getItem('fidesia_level') || 'initie';
        this.responseLength = localStorage.getItem('fidesia_length') || 'synthetique';

        // Bind age buttons
        document.querySelectorAll('#age-options .profile-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.ageGroup = btn.dataset.value;
                localStorage.setItem('fidesia_age', this.ageGroup);
                this._updateButtons('#age-options', this.ageGroup);
            });
        });

        // Bind level buttons
        document.querySelectorAll('#level-options .profile-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.knowledgeLevel = btn.dataset.value;
                localStorage.setItem('fidesia_level', this.knowledgeLevel);
                this._updateButtons('#level-options', this.knowledgeLevel);
            });
        });

        // Bind length buttons
        document.querySelectorAll('#length-options .profile-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.responseLength = btn.dataset.value;
                localStorage.setItem('fidesia_length', this.responseLength);
                this._updateButtons('#length-options', this.responseLength);
            });
        });

        // Set initial active states
        this._updateButtons('#age-options', this.ageGroup);
        this._updateButtons('#level-options', this.knowledgeLevel);
        this._updateButtons('#length-options', this.responseLength);

        // Backdrop close
        document.querySelector('#profile-modal .modal-backdrop').addEventListener('click', () => this.close());
    },

    open() {
        document.getElementById('profile-modal').hidden = false;
    },

    close() {
        document.getElementById('profile-modal').hidden = true;
    },

    _updateButtons(selector, value) {
        document.querySelectorAll(`${selector} .profile-btn`).forEach(btn => {
            btn.classList.toggle('active', btn.dataset.value === value);
        });
    }
};
