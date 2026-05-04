createVueApp({
    data() {
        return {
            stats: {monitor_count: '-', account_count: '-'},
            accounts: [],
            selectedAccount: 'all',
            importMode: 'overwrite',
            previewText: ''
        };
    },
    methods: {
        accountLabel(account) {
            return account.phone ? `${account.phone} (${account.account_id})` : account.account_id;
        },
        async loadAccounts() {
            try {
                const data = await apiJson('/api/accounts');
                this.accounts = data.accounts || [];
            } catch (error) {
                showNotification(`加载账号列表失败: ${error.message}`, 'error');
            }
        },
        async loadStats() {
            try {
                const data = await apiJson('/api/config/stats');
                this.stats = data.success && data.stats
                    ? data.stats
                    : {monitor_count: '-', account_count: '-'};
            } catch {
                this.stats = {monitor_count: '错误', account_count: '错误'};
            }
        },
        showPreview(config) {
            this.previewText = JSON.stringify(config, null, 2);
        },
        saveJson(content, filename) {
            downloadBlob(new Blob([content], {type: 'application/json'}), filename);
        },
        async exportConfig() {
            if (!this.selectedAccount) {
                showNotification('请选择要导出的账号', 'error');
                return;
            }

            try {
                const data = await apiJson(`/api/export/config?accounts=${encodeURIComponent(this.selectedAccount)}`);
                const content = JSON.stringify(data, null, 2);
                this.showPreview(data);
                this.saveJson(content, `system_config_${Date.now()}.json`);
                showNotification('配置导出成功', 'success');
            } catch (error) {
                showNotification(`导出配置失败: ${error.message}`, 'error');
            }
        },
        async importConfig(event) {
            const file = event.target.files && event.target.files[0];
            if (!file) return;

            try {
                const config = JSON.parse(await file.text());
                this.showPreview(config);
                const modeText = this.importMode === 'overwrite' ? '覆盖现有配置' : '合并到现有配置';
                if (!confirm(`确定要导入此配置吗？这将${modeText}。`)) return;

                await apiSend('/api/import/config', {config, mode: this.importMode});
                showNotification(`配置导入成功 (${modeText})`, 'success');
                setTimeout(() => location.reload(), 1500);
            } catch (error) {
                showNotification(`导入配置失败: ${error.message}`, 'error');
            } finally {
                event.target.value = '';
            }
        },
        copyConfig() {
            navigator.clipboard.writeText(this.previewText)
                .then(() => showNotification('配置已复制到剪贴板', 'success'))
                .catch(() => showNotification('复制失败', 'error'));
        },
        downloadConfig() {
            this.saveJson(this.previewText, `system_config_${Date.now()}.json`);
        }
    },
    mounted() {
        this.loadStats();
        this.loadAccounts();
    }
}).mount('#config-export-app');
