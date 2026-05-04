createVueApp({
    data() {
        return {
            accounts: [],
            accountId: '',
            channels: [],
            search: '',
            filter: 'all',
            loading: false,
            currentPage: 1,
            itemsPerPage: 50,
            emptyTitle: '暂无目标数据',
            emptyDescription: '请选择账号并加载目标列表',
            filters: [
                {value: 'all', label: '全部'},
                {value: 'channel', label: '目标', icon: 'bi bi-broadcast'},
                {value: 'group', label: '会话', icon: 'bi bi-people'},
                {value: 'bot', label: 'Bot', icon: 'bi bi-robot'},
                {value: 'user', label: '私聊', icon: 'bi bi-person'}
            ]
        };
    },
    computed: {
        counts() {
            return {
                all: this.channels.length,
                channel: this.channels.filter(c => c.type === 'channel').length,
                group: this.channels.filter(c => c.type === 'group').length,
                bot: this.channels.filter(c => c.type === 'bot').length,
                user: this.channels.filter(c => c.type === 'user').length
            };
        },
        filteredChannels() {
            const term = this.search.toLowerCase();
            return this.channels.filter(channel => {
                const matchesSearch = !term
                    || String(channel.name || '').toLowerCase().includes(term)
                    || String(channel.description || '').toLowerCase().includes(term)
                    || String(channel.username || '').toLowerCase().includes(term);
                const matchesType = this.filter === 'all' || channel.type === this.filter;
                return matchesSearch && matchesType;
            });
        },
        pagination() {
            return pageData(this.filteredChannels, this.currentPage, this.itemsPerPage);
        },
        totalPages() {
            return this.pagination.totalPages;
        },
        pagedChannels() {
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
    watch: {
        search() {
            this.currentPage = 1;
        },
        filter() {
            this.currentPage = 1;
        }
    },
    methods: {
        async loadAccounts() {
            try {
                const data = await apiJson('/api/accounts');
                this.accounts = data.accounts || [];
                if (this.accounts.length) {
                    this.accountId = this.accounts[0].account_id;
                    showNotification('点击"加载目标"按钮查看目标列表', 'info');
                }
            } catch {
                showNotification('加载账号失败', 'error');
            }
        },
        async loadChannels() {
            if (!this.accountId) {
                showNotification('请先选择一个账号', 'warning');
                return;
            }
            if (this.loading) return;

            this.loading = true;
            this.channels = [];
            this.currentPage = 1;
            this.filter = 'all';
            try {
                const data = await apiJson(`/api/accounts/${encodeURIComponent(this.accountId)}/channels?fetch_all=1`);
                if (data.success === false) throw new Error(data.error || '服务器返回错误');
                this.channels = data.channels || [];
                this.emptyTitle = this.channels.length ? '' : '该账号暂无群组或频道';
                this.emptyDescription = this.channels.length ? '' : '可能是新账号或未加入任何目标';
                showNotification(`成功加载 ${this.channels.length} 个目标`, 'success');
            } catch (error) {
                this.emptyTitle = '加载失败';
                this.emptyDescription = error.message || '网络错误，请重试';
                showNotification(`加载目标失败: ${this.emptyDescription}`, 'error');
            } finally {
                this.loading = false;
            }
        },
        setFilter(value) {
            this.filter = value;
        },
        countFor(value) {
            return this.counts[value] || 0;
        },
        changePage(page) {
            if (page >= 1 && page <= this.totalPages) this.currentPage = page;
        },
        typeName(type) {
            return {channel: '频道', group: '群组', bot: 'Bot', user: '私聊'}[type] || '目标';
        },
        initial(channel) {
            return String(channel.name || '?').charAt(0).toUpperCase();
        },
        isHttp(link) {
            return String(link || '').startsWith('http');
        },
        async copyId(id) {
            try {
                await navigator.clipboard.writeText(String(id));
                showNotification('ID已复制到剪贴板', 'success');
            } catch {
                showNotification('复制失败', 'error');
            }
        },
        exportChannels() {
            if (!this.channels.length) {
                showNotification('暂无目标数据可导出', 'warning');
                return;
            }
            const account = this.accounts.find(item => item.account_id === this.accountId);
            const data = {
                export_time: new Date().toISOString(),
                account: {id: this.accountId, name: account ? `${account.phone} (${account.account_id})` : this.accountId},
                channels: this.channels
            };
            downloadJson(data, `channels_${this.accountId}_${Date.now()}.json`);
            showNotification('目标列表导出成功', 'success');
        }
    },
    mounted() {
        this.loadAccounts();
    }
}).mount('#channels-app');
