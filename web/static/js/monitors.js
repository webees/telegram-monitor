createVueApp({
    data() {
        return {
            accounts: [],
            currentAccount: '',
            monitors: [],
            currentFilter: 'all',
            currentPage: 1,
            itemsPerPage: 10,
            loading: false,
            selectedMonitor: null,
            filterItems: [
                {value: 'all', label: '全部', countKey: 'total'},
                {value: 'KeywordMonitor', label: '关键词规则', countKey: 'keyword'},
                {value: 'FileMonitor', label: '文件规则', countKey: 'file'},
                {value: 'ButtonMonitor', label: '按钮规则', countKey: 'button'},
                {value: 'ImageButtonMonitor', label: '图片按钮规则', countKey: 'imageButton'},
                {value: 'AIMonitor', label: 'AI规则', countKey: 'ai'},
                {value: 'AllMessagesMonitor', label: '全量规则', countKey: 'allMessages'}
            ]
        };
    },
    computed: {
        typeCounts() {
            return {
                total: this.monitors.length,
                keyword: this.countType('KeywordMonitor'),
                file: this.countType('FileMonitor'),
                button: this.countType('ButtonMonitor'),
                imageButton: this.countType('ImageButtonMonitor'),
                ai: this.countType('AIMonitor'),
                allMessages: this.countType('AllMessagesMonitor')
            };
        },
        filteredMonitors() {
            return this.currentFilter === 'all'
                ? this.monitors
                : this.monitors.filter(monitor => monitor.monitor_type === this.currentFilter);
        },
        pagination() {
            return pageData(this.filteredMonitors, this.currentPage, this.itemsPerPage);
        },
        totalPages() {
            return this.pagination.totalPages;
        },
        pagedMonitors() {
            return this.pagination.items;
        },
        visiblePages() {
            return this.pagination.pages;
        },
        pageStart() {
            return this.pagination.start;
        },
        pageEnd() {
            return this.pagination.end;
        },
        currentVisiblePage() {
            return this.pagination.current;
        }
    },
    methods: {
        countType(type) {
            return this.monitors.filter(monitor => monitor.monitor_type === type).length;
        },
        async loadAccounts() {
            try {
                const data = await apiJson('/api/accounts');
                this.accounts = data.accounts || [];
                const queryAccount = new URLSearchParams(location.search).get('account');
                const selected = this.accounts.find(account => account.account_id === queryAccount) || this.accounts[0];
                if (selected) {
                    this.currentAccount = selected.account_id;
                    await this.loadMonitors();
                }
            } catch {
                showNotification('加载账号失败', 'error');
            }
        },
        async selectAccount() {
            this.currentFilter = 'all';
            this.currentPage = 1;
            if (this.currentAccount) {
                await this.loadMonitors();
            } else {
                this.monitors = [];
            }
        },
        async loadMonitors() {
            if (!this.currentAccount) return;
            this.loading = true;
            try {
                this.monitors = await apiJson(`/api/monitors/${encodeURIComponent(this.currentAccount)}`);
            } catch (error) {
                showNotification(`加载规则失败: ${error.message}`, 'error');
            } finally {
                this.loading = false;
            }
        },
        refresh() {
            this.currentAccount ? this.loadMonitors() : this.loadAccounts();
        },
        setFilter(value) {
            this.currentFilter = value;
            this.currentPage = 1;
        },
        changePage(page) {
            if (page >= 1 && page <= this.totalPages) this.currentPage = page;
        },
        typeName(type) {
            return {
                KeywordMonitor: '关键词规则',
                FileMonitor: '文件规则',
                AIMonitor: 'AI规则',
                ButtonMonitor: '按钮规则',
                ImageButtonMonitor: '图片按钮规则',
                AllMessagesMonitor: '全量规则'
            }[type] || '未知类型';
        },
        displayName(monitor) {
            const config = monitor.config || {};
            if (monitor.monitor_type === 'KeywordMonitor') return config.keyword || monitor.key;
            if (monitor.monitor_type === 'FileMonitor') return config.file_extension || config.extension || monitor.key;
            if (monitor.monitor_type === 'AIMonitor') return `AI规则: ${monitor.key}`;
            if (monitor.monitor_type === 'ButtonMonitor') return `按钮: ${config.button_text || config.button_keyword || monitor.key}`;
            if (monitor.monitor_type === 'ImageButtonMonitor') return `图片按钮: ${config.button_text || monitor.key}`;
            return monitor.key;
        },
        isLimited(monitor) {
            return monitor.max_executions && monitor.execution_count >= monitor.max_executions;
        },
        isActive(monitor) {
            return (monitor.config || {}).active !== false;
        },
        priority(monitor) {
            return (monitor.config || {}).priority || 50;
        },
        statusText(monitor) {
            if (!this.isActive(monitor)) return '已暂停';
            if (this.isLimited(monitor)) return '已达限制';
            return '活跃';
        },
        toggleTitle(monitor) {
            return this.isActive(monitor) ? '暂停' : '启动';
        },
        executionText(monitor) {
            return `${monitor.execution_count || 0}${monitor.max_executions ? ` / ${monitor.max_executions}` : ''}`;
        },
        formatDate(dateStr) {
            return new Date(dateStr || Date.now()).toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        },
        createNewMonitor() {
            location.href = `/wizard?new=true&timestamp=${Date.now()}`;
        },
        editMonitor(monitor) {
            const typeMap = {
                KeywordMonitor: 'keyword',
                FileMonitor: 'file',
                AllMessagesMonitor: 'all_messages',
                ButtonMonitor: 'button',
                ImageButtonMonitor: 'image_button',
                AIMonitor: 'ai'
            };
            const type = typeMap[monitor.monitor_type];
            if (!type) {
                showNotification('未知的规则类型', 'error');
                return;
            }
            const config = encodeURIComponent(JSON.stringify(monitor.config || {})).replace(/'/g, '%27');
            location.href = `/wizard?type=${type}&edit=true&key=${encodeURIComponent(monitor.key)}&config=${config}&account_id=${encodeURIComponent(monitor.account_id || this.currentAccount)}`;
        },
        viewConfig(monitor) {
            this.selectedMonitor = monitor;
        },
        jsonConfig(config) {
            return JSON.stringify(config || {}, null, 2);
        },
        yesNo(value) {
            return value ? '已启用' : '未启用';
        },
        list(value) {
            return Array.isArray(value) && value.length ? value.join(', ') : '未设置';
        },
        configRows(monitor) {
            const config = monitor.config || {};
            return [
                {label: '类型', value: this.typeName(monitor.monitor_type)},
                {label: '状态', value: config.active !== false ? '运行中' : '已暂停'},
                {label: '适用范围', value: this.list(config.chats)},
                {label: '自动转发', value: this.yesNo(config.auto_forward)},
                {label: '转发目标', value: this.list(config.forward_targets)},
                {label: '智能追加', value: this.yesNo(config.forward_rewrite_enabled)},
                {label: '自动回复', value: this.yesNo(config.reply_enabled)},
                {label: '执行限制', value: config.max_executions || '无限制'},
                {label: '转发文案模板', value: config.forward_rewrite_template || '未设置'}
            ];
        },
        async deleteMonitor(monitorKey) {
            if (!confirm('确定要删除这个规则吗？此操作不可撤销。')) return;
            try {
                const result = await apiJson(`/api/monitors/${encodeURIComponent(this.currentAccount)}/${encodeURIComponent(monitorKey)}`, {
                    method: 'DELETE'
                });
                showNotification(result.success ? '规则删除成功' : '删除失败', result.success ? 'success' : 'error');
                if (result.success) await this.loadMonitors();
            } catch (error) {
                showNotification(`删除失败: ${error.message}`, 'error');
            }
        },
        async toggleStatus(monitor) {
            const active = this.isActive(monitor);
            if (!confirm(`确定要${active ? '暂停' : '启动'}这个规则吗？`)) return;
            try {
                const result = await apiSend(`/api/monitors/${encodeURIComponent(this.currentAccount)}/${encodeURIComponent(monitor.key)}/toggle`, {active: !active}, 'PUT');
                showNotification(result.message || `规则已${!active ? '启动' : '暂停'}`, 'success');
                await this.loadMonitors();
            } catch (error) {
                showNotification(`状态更新失败: ${error.message}`, 'error');
            }
        }
    },
    mounted() {
        this.loadAccounts();
    }
}).mount('#monitors-app');
