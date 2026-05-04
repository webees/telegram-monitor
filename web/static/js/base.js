(() => {
    window.createVueApp = options => {
        if (!window.Vue) {
            throw new Error('Vue 未加载');
        }
        return Vue.createApp({delimiters: ['[[', ']]'], ...options});
    };

    window.apiJson = async (url, options) => {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => ({}));
        if (response.status === 401) location.href = '/login';
        if (!response.ok) throw new Error(data.detail || data.message || data.error || `HTTP ${response.status}`);
        return data;
    };

    window.apiSend = (url, body = {}, method = 'POST') => window.apiJson(url, {
        method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    });

    window.downloadBlob = (blob, filename) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    window.downloadJson = (data, filename) => {
        window.downloadBlob(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}), filename);
    };

    window.pageData = (items, currentPage, perPage) => {
        const list = items || [];
        const size = Math.max(1, perPage || 10);
        const totalPages = Math.ceil(list.length / size);
        const page = Math.min(Math.max(1, currentPage || 1), Math.max(1, totalPages));
        const startIndex = (page - 1) * size;
        const start = list.length ? startIndex + 1 : 0;
        const end = Math.min(page * size, list.length);
        const pages = [];
        for (let n = Math.max(1, page - 2); n <= Math.min(totalPages, page + 2); n += 1) pages.push(n);
        return {items: list.slice(startIndex, startIndex + size), totalPages, pages, start, end, current: page};
    };

    window.showNotification = (message, type = 'info') => {
        const box = document.createElement('div');
        box.className = `alert alert-${type}`;
        const row = document.createElement('div');
        const text = document.createElement('span');
        const close = document.createElement('button');
        row.className = 'flex items-start gap-2';
        text.className = 'flex-1';
        text.textContent = message;
        close.type = 'button';
        close.dataset.action = 'close-alert';
        close.textContent = 'x';
        row.append(text, close);
        box.appendChild(row);
        const area = document.getElementById('notification-area');
        if (area) area.appendChild(box);
        setTimeout(() => box.remove(), 5000);
    };

    let currentSystemStatus = '';

    window.setSystemStatus = status => {
        const statusKey = status || 'running';
        if (statusKey === currentSystemStatus) return;

        const indicator = document.querySelector('.status-indicator');
        const text = document.querySelector('.status-text');
        if (!indicator || !text) return;

        const map = {
            running: ['bg-green-500', '系统运行中'],
            '运行中': ['bg-green-500', '系统运行中'],
            stopped: ['bg-red-500', '系统已停止'],
            '已停止': ['bg-red-500', '系统已停止'],
            partial: ['bg-amber-500', '部分连接'],
            '部分连接': ['bg-amber-500', '部分连接'],
            unconfigured: ['bg-slate-400', '未配置'],
            '未配置': ['bg-slate-400', '未配置'],
        };
        const [color, label] = map[statusKey] || map.running;
        indicator.className = `status-indicator h-2 w-2 rounded-full ${color}`;
        text.textContent = label;
        currentSystemStatus = statusKey;
    };

    window.updateSystemStats = (stats = {}) => {
        const uptime = document.getElementById('uptime');
        if (stats.uptime && uptime && uptime.textContent !== stats.uptime) uptime.textContent = stats.uptime;
        window.setSystemStatus(stats.status);
        window.dispatchEvent(new CustomEvent('system-stats', {detail: stats}));
        if (window.dashboardApp && window.dashboardApp.updateStats) window.dashboardApp.updateStats(stats);
    };

    window.loadStats = () => {
        window.apiJson('/api/stats')
            .then(window.updateSystemStats)
            .catch(() => window.setSystemStatus('partial'));
    };

    window.logout = () => {
        if (!confirm('确定要退出登录吗？')) return;
        fetch('/logout', {method: 'POST'}).finally(() => location.href = '/login');
    };

    document.addEventListener('click', event => {
        const actionEl = event.target.closest('[data-action]');
        const action = actionEl && actionEl.dataset.action;
        if (action === 'close-alert') {
            const alert = event.target.closest('.alert');
            if (alert) alert.remove();
        }
        if (action === 'refresh-status') window.loadStats();
        if (action === 'logout') window.logout();
    });

    document.addEventListener('DOMContentLoaded', () => {
        const toggle = document.getElementById('mobileMenuToggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        if (toggle) toggle.addEventListener('click', () => {
            if (sidebar) sidebar.classList.toggle('-translate-x-full');
            if (overlay) overlay.classList.toggle('hidden');
        });
        if (overlay) overlay.addEventListener('click', () => {
            if (sidebar) sidebar.classList.add('-translate-x-full');
            overlay.classList.add('hidden');
        });
        window.loadStats();
    });
})();
