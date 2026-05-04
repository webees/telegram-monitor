(() => {
    const number = new Intl.NumberFormat('zh-CN');
    const value = (primary, fallback, defaultValue = 0) => {
        if (primary !== undefined && primary !== null) return primary;
        if (fallback !== undefined && fallback !== null) return fallback;
        return defaultValue;
    };

    window.dashboardApp = createVueApp({
        data() {
            return {
                totalAccounts: '-',
                monitorCount: '-',
                processedMessages: '-',
                runtime: '-',
                cpu: 0,
                memory: 0,
                memoryUsed: 0,
                disk: 0,
                networkStatus: '加载中...'
            };
        },
        computed: {
            memoryText() {
                return `${this.memoryUsed} MB (${this.memory}%)`;
            }
        },
        methods: {
            updateStats(data = {}) {
                this.totalAccounts = value(data.total_accounts, data.account_count);
                this.monitorCount = value(data.total_monitors, data.monitor_count);
                this.processedMessages = number.format(value(data.processed_messages));
                this.runtime = data.uptime || '-';
                this.cpu = Math.round(value(data.cpu_percent));
                this.memory = Math.round(value(data.memory_percent));
                this.memoryUsed = Math.round(value(data.memory_used_mb));
                this.disk = Math.round(value(data.disk_usage_percent));
                this.networkStatus = data.network_status || '未知';
            }
        },
        mounted() {
            window.addEventListener('system-stats', event => this.updateStats(event.detail || {}));
        }
    }).mount('#dashboard-app');
})();
