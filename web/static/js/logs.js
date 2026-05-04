createVueApp({
    data() {
        return {
            allLogs: [],
            currentFilter: 'all',
            loading: false,
            error: '',
            filters: [
                {value: 'all', label: '全部'},
                {value: 'error', label: '错误'},
                {value: 'warning', label: '警告'},
                {value: 'info', label: '信息'},
                {value: 'debug', label: '调试'}
            ]
        };
    },
    computed: {
        stats() {
            return {
                total: this.allLogs.length,
                error: this.allLogs.filter(log => log.level === 'ERROR').length,
                warning: this.allLogs.filter(log => log.level === 'WARNING').length,
                info: this.allLogs.filter(log => log.level === 'INFO').length
            };
        },
        visibleLogs() {
            const filtered = this.currentFilter === 'all'
                ? this.allLogs
                : this.allLogs.filter(log => String(log.level || '').toLowerCase() === this.currentFilter);

            return filtered.filter(log => !this.isNoise(log));
        }
    },
    watch: {
        visibleLogs() {
            this.scrollToBottom();
        }
    },
    methods: {
        isNoise(log) {
            const message = log.message || '';
            return log.source === 'uvicorn'
                || log.source === 'uvicorn.access'
                || message.includes('GET /api/')
                || message.includes('POST /api/')
                || message.includes('PUT /api/')
                || message.includes('DELETE /api/')
                || message.includes('HTTP/1.1')
                || message.includes('获取日志')
                || message.includes('读取日志文件');
        },
        formatTime(timestamp) {
            return new Date(timestamp).toLocaleString('zh-CN', {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        },
        async loadLogs() {
            this.loading = true;
            this.error = '';
            try {
                const data = await apiJson('/api/logs?limit=1000');
                if (!data.success) throw new Error(data.message || '获取日志失败');
                this.allLogs = data.logs || [];
                this.scrollToBottom();
            } catch (error) {
                this.error = error.message;
            } finally {
                this.loading = false;
            }
        },
        async refreshLogs() {
            await this.loadLogs();
            if (!this.error) showNotification('日志已刷新', 'success');
        },
        async clearLogs() {
            if (!confirm('确定要清空所有日志吗？这将删除服务器上的日志文件内容，此操作不可恢复。')) return;

            try {
                await apiJson('/api/logs/clear', {method: 'DELETE'});
                this.allLogs = [];
                showNotification('日志已清空', 'success');
            } catch (error) {
                showNotification(`清空日志失败: ${error.message}`, 'error');
            }
        },
        async downloadLogs() {
            try {
                const response = await fetch('/api/logs/download');
                if (!response.ok) throw new Error('下载失败');
                const blob = await response.blob();
                downloadBlob(blob, `system_logs_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.log`);
                showNotification('日志文件下载成功', 'success');
            } catch (error) {
                showNotification(`下载日志失败: ${error.message}`, 'error');
            }
        },
        scrollToBottom() {
            this.$nextTick(() => {
                if (this.$refs.viewer) this.$refs.viewer.scrollTop = this.$refs.viewer.scrollHeight;
            });
        }
    },
    mounted() {
        this.loadLogs();
    }
}).mount('#logs-app');
