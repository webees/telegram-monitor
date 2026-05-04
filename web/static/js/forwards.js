createVueApp({
    data() {
        return {
            status: '',
            records: [],
            loading: false
        };
    },
    methods: {
        statusText(status) {
            return {success: '成功', failed: '失败', pending: '等待'}[status] || status;
        },
        shortError(error) {
            return String(error || '').slice(0, 80);
        },
        async load() {
            this.loading = true;
            try {
                const statusQuery = this.status ? `&status=${encodeURIComponent(this.status)}` : '';
                const data = await apiJson(`/api/forwards?limit=500${statusQuery}`);
                this.records = data.records || [];
            } catch (error) {
                showNotification(`加载转发列表失败: ${error.message}`, 'error');
            } finally {
                this.loading = false;
            }
        },
        async retry(id) {
            try {
                const result = await apiJson(`/api/forwards/${encodeURIComponent(id)}/retry`, {method: 'POST'});
                showNotification(result.success ? '已提交重试' : (result.message || '重试失败'), result.success ? 'success' : 'error');
                await this.load();
            } catch (error) {
                showNotification(`重试失败: ${error.message}`, 'error');
            }
        }
    },
    mounted() {
        this.load();
    }
}).mount('#forwards-app');
