let currentUnfollowUser = null;
let pollInterval = null;

function toggleModal(show) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    if (show) {
        overlay.classList.remove('opacity-0', 'pointer-events-none');
        overlay.classList.add('opacity-100');
        content.classList.remove('scale-95');
        content.classList.add('scale-100');
    } else {
        overlay.classList.remove('opacity-100');
        overlay.classList.add('opacity-0', 'pointer-events-none');
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
        currentUnfollowUser = null;
    }
}

function updateStats(data) {
    document.getElementById('stat-following').textContent = data.following || 0;
    document.getElementById('stat-followers').textContent = data.followers || 0;
    document.getElementById('stat-nonfollowers').textContent = data.non_followers ? data.non_followers.length : 0;
    document.getElementById('records-badge').textContent = (data.non_followers ? data.non_followers.length : 0) + ' Records';
    document.getElementById('account-label').textContent = '@' + (data.username || 'unknown');
}

function renderList(users) {
    const container = document.getElementById('nonfollowers-list');
    container.innerHTML = '';
    if (!users || users.length === 0) {
        container.innerHTML = '<div class="glass-card p-6 rounded-xl text-center"><p class="font-body-md text-on-surface-variant">No non-followers found. Everyone follows you back!</p></div>';
        return;
    }
    users.forEach((user, i) => {
        const div = document.createElement('div');
        div.className = 'flex items-center gap-6 p-4 glass-card rounded-xl group';
        div.innerHTML = `
            <span class="w-8 font-label-md text-[12px] text-on-surface-variant/40 group-hover:text-primary transition-colors font-bold">${String(i + 1).padStart(2, '0')}</span>
            <div class="flex-1 min-w-0">
                <p class="font-body-md text-[16px] font-bold text-on-surface truncate tracking-tight group-hover:text-primary transition-colors">@${escHtml(user.username)}</p>
                <p class="font-label-md text-[11px] text-on-surface-variant truncate uppercase tracking-[0.1em] mt-0.5">${escHtml(user.full_name)}</p>
            </div>
            <div class="flex items-center gap-8">
                <a class="hidden sm:flex items-center gap-2 text-on-surface-variant font-label-md text-[11px] hover:text-primary transition-colors uppercase tracking-widest font-bold" href="https://www.instagram.com/${escHtml(user.username)}/" target="_blank" rel="noopener">
                    Profile
                    <span class="material-symbols-outlined text-[16px]">open_in_new</span>
                </a>
                <button class="px-6 py-2.5 bg-error/10 text-error border border-error/20 font-label-md text-[11px] font-bold rounded-lg hover:bg-error hover:text-white transition-all uppercase tracking-widest active:scale-95" data-pk="${user.pk}" data-username="${escHtml(user.username)}">
                    Unfollow
                </button>
            </div>
        `;
        container.appendChild(div);
    });

    container.querySelectorAll('button[data-pk]').forEach(btn => {
        btn.addEventListener('click', () => {
            currentUnfollowUser = { pk: parseInt(btn.dataset.pk), username: btn.dataset.username };
            document.getElementById('modal-username').textContent = '@' + btn.dataset.username;
            toggleModal(true);
        });
    });
}

function escHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

async function loadResults() {
    try {
        const res = await fetch('/api/results');
        const data = await res.json();
        if (data.ok) {
            updateStats(data);
            renderList(data.non_followers);
            if (data.non_followers && data.non_followers.length > 0) {
                document.getElementById('results-section').style.display = 'flex';
            }
        }
    } catch (e) {
        console.error('Failed to load results', e);
    }
}

async function startFetch() {
    const btn = document.getElementById('fetch-btn');
    btn.disabled = true;
    btn.textContent = 'Fetching...';

    document.getElementById('progress-section').style.display = 'block';
    document.getElementById('results-section').style.display = 'none';

    try {
        const res = await fetch('/api/fetch', { method: 'POST' });
        const data = await res.json();
        if (!data.ok) {
            alert(data.error || 'Fetch failed');
            btn.disabled = false;
            btn.textContent = 'Fetch Data';
            return;
        }
    } catch (e) {
        alert('Network error');
        btn.disabled = false;
        btn.textContent = 'Fetch Data';
        return;
    }

    pollInterval = setInterval(pollStatus, 1000);
}

async function pollStatus() {
    try {
        const res = await fetch('/api/fetch-status');
        const status = await res.json();

        const label = document.getElementById('progress-label');
        const count = document.getElementById('progress-count');
        const bar = document.getElementById('progress-bar');
        const btn = document.getElementById('fetch-btn');

        if (status.running) {
            const phaseLabels = {
                'starting': 'Initializing...',
                'followers': 'Scanning followers',
                'following': 'Scanning following',
                'analyzing': 'Analyzing results',
            };
            label.textContent = phaseLabels[status.phase] || 'Processing...';
            count.textContent = status.current + ' fetched';
            bar.style.width = Math.min(status.current / 5, 95) + '%';
        } else {
            clearInterval(pollInterval);
            pollInterval = null;
            btn.disabled = false;
            btn.textContent = 'Fetch Data';

            if (status.phase === 'done') {
                label.textContent = 'Analysis complete';
                count.textContent = 'Done';
                bar.style.width = '100%';
                bar.className = 'h-full bg-gradient-to-r from-secondary to-primary w-full transition-all duration-500 ease-in-out shadow-[0_0_15px_rgba(0,209,102,0.4)]';
                await loadResults();
            } else if (status.phase === 'error') {
                label.textContent = 'Error: ' + (status.error || 'Unknown error');
                label.className = 'font-label-md text-[12px] font-bold text-error tracking-wide';
                count.textContent = 'Failed';
                bar.style.width = '0%';
                document.getElementById('progress-section').style.display = 'none';
            }
        }
    } catch (e) {
        console.error('Poll error', e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fetch-btn').addEventListener('click', startFetch);

    document.getElementById('modal-abort').addEventListener('click', () => toggleModal(false));
    document.getElementById('modal-confirm').addEventListener('click', async () => {
        if (!currentUnfollowUser) return;
        toggleModal(false);
        try {
            const res = await fetch('/api/unfollow', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: currentUnfollowUser.pk }),
            });
            const data = await res.json();
            if (data.ok) {
                await loadResults();
            } else {
                alert('Failed to unfollow: ' + (data.error || 'Unknown error'));
            }
        } catch (e) {
            alert('Network error');
        }
    });

    document.getElementById('logout-link').addEventListener('click', async (e) => {
        e.preventDefault();
        await fetch('/api/logout', { method: 'POST' });
        window.location.href = '/';
    });

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') toggleModal(false);
    });

    loadResults();

    // Auto-refresh: always trigger a fresh fetch on dashboard load
    setTimeout(async () => {
        const btn = document.getElementById('fetch-btn');
        if (btn && !btn.disabled) {
            btn.disabled = true;
            btn.textContent = 'Auto...';
            document.getElementById('progress-section').style.display = 'block';
            try {
                const res = await fetch('/api/fetch', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    pollInterval = setInterval(pollStatus, 1000);
                } else {
                    btn.disabled = false;
                    btn.textContent = 'Fetch Data';
                    document.getElementById('progress-section').style.display = 'none';
                }
            } catch (e) {
                btn.disabled = false;
                btn.textContent = 'Fetch Data';
                document.getElementById('progress-section').style.display = 'none';
            }
        }
    }, 500);
});
