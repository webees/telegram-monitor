createVueApp({
    data() {
        return {
            accounts: [],
            loading: false,
            modal: '',
            pendingAccountId: '',
            verifyCode: '',
            password: '',
            showPassword: false,
            addForm: {
                phone: '',
                api_id: '',
                api_hash: '',
                proxy_type: '',
                proxy_address: ''
            }
        };
    },
    computed: {
        statCards() {
            const total = this.accounts.length;
            const online = this.accounts.filter(a => a.is_valid && a.monitor_active).length;
            const offline = this.accounts.filter(a => a.is_valid && !a.monitor_active).length;
            const invalid = this.accounts.filter(a => !a.is_valid).length;
            return [
                {label: '总账号数', value: total, footer: '已添加的所有账号', icon: 'bi bi-people'},
                {label: '在线账号', value: online, footer: '正常连接中', icon: 'bi bi-check-circle'},
                {label: '离线账号', value: offline, footer: '需要重新连接', icon: 'bi bi-x-circle'},
                {label: '失效账号', value: invalid, footer: '需要重新登录', icon: 'bi bi-exclamation-triangle', extraClass: 'border-l-4 border-pink-500'}
            ];
        }
    },
    methods: {
        accountInitial(account) {
            return account.name ? account.name.charAt(0).toUpperCase() : String(account.phone || '--').slice(-2);
        },
        accountDotClass(account) {
            if (account.is_valid && account.monitor_active) return '';
            if (account.is_valid) return 'offline';
            return account.status || 'error';
        },
        resetAddForm() {
            this.addForm = {phone: '', api_id: '', api_hash: '', proxy_type: '', proxy_address: ''};
        },
        async loadAccounts() {
            this.loading = true;
            try {
                const data = await apiJson('/api/accounts');
                this.accounts = data.accounts || [];
            } catch (error) {
                showNotification('加载账号列表失败', 'error');
            } finally {
                this.loading = false;
            }
        },
        async openAddModal() {
            this.modal = 'add';
            try {
                const data = await apiJson('/api/config/defaults');
                if (data.success) {
                    this.addForm.api_id = data.api_id || this.addForm.api_id;
                    this.addForm.api_hash = data.api_hash || this.addForm.api_hash;
                }
            } catch {
                // 默认配置读取失败不影响手动填写。
            }
        },
        closeAddModal() {
            this.modal = '';
            this.resetAddForm();
        },
        proxyPayload() {
            if (!this.addForm.proxy_type || !this.addForm.proxy_address.includes(':')) return {};
            const [host, port] = this.addForm.proxy_address.split(':');
            return {
                proxy_type: this.addForm.proxy_type,
                proxy_host: host,
                proxy_port: parseInt(port, 10)
            };
        },
        async submitAddAccount() {
            if (!this.$refs.addForm.reportValidity()) return;
            const payload = {
                phone: this.addForm.phone,
                api_id: parseInt(this.addForm.api_id, 10),
                api_hash: this.addForm.api_hash,
                ...this.proxyPayload()
            };
            try {
                const result = await apiSend('/api/accounts', payload);

                if (!result.success) {
                    showNotification(result.message || '添加失败', 'error');
                    return;
                }
                if (result.step === 'verify_code') {
                    this.pendingAccountId = payload.phone;
                    this.closeAddModal();
                    this.modal = 'code';
                    showNotification(result.message || '验证码已发送', 'info');
                    return;
                }
                this.closeAddModal();
                showNotification(result.message || '账号添加成功', 'success');
                this.loadAccounts();
            } catch (error) {
                showNotification('添加账号失败，请重试', 'error');
            }
        },
        async submitVerifyCode() {
            if (!this.$refs.codeForm.reportValidity()) return;
            try {
                const result = await apiSend('/api/accounts/verify', {account_id: this.pendingAccountId, code: this.verifyCode});

                if (!result.success) {
                    showNotification(result.message || '验证失败', 'error');
                    return;
                }
                this.verifyCode = '';
                if (result.step === 'password') {
                    this.modal = 'password';
                    showNotification(result.message || '请输入两步验证密码', 'info');
                    return;
                }
                this.modal = '';
                showNotification(result.message || '账号添加成功', 'success');
                this.loadAccounts();
            } catch {
                showNotification('验证失败，请重试', 'error');
            }
        },
        async submitPassword() {
            if (!this.$refs.passwordForm.reportValidity()) return;
            try {
                const result = await apiSend('/api/accounts/password', {account_id: this.pendingAccountId, password: this.password});

                if (!result.success) {
                    showNotification(result.message || '密码验证失败', 'error');
                    return;
                }
                this.modal = '';
                this.password = '';
                showNotification(result.message || '账号添加成功', 'success');
                this.loadAccounts();
            } catch {
                showNotification('验证失败，请重试', 'error');
            }
        },
        async toggleAccount(accountId) {
            try {
                const result = await apiJson(`/api/accounts/${encodeURIComponent(accountId)}/toggle`, {method: 'POST'});
                showNotification(result.success ? '账号状态已更新' : '操作失败，请重试', result.success ? 'success' : 'error');
                if (result.success) this.loadAccounts();
            } catch {
                showNotification('操作失败，请重试', 'error');
            }
        },
        async deleteAccount(accountId, phone) {
            if (!confirm(`确定要删除账号 ${phone} 吗？此操作将删除该账号的所有规则配置，不可恢复！`)) return;
            try {
                const result = await apiJson(`/api/accounts/${encodeURIComponent(accountId)}`, {method: 'DELETE'});
                showNotification(result.message || (result.success ? '账号删除成功' : '删除失败'), result.success ? 'success' : 'error');
                if (result.success) this.loadAccounts();
            } catch {
                showNotification('删除失败，请重试', 'error');
            }
        },
        goMonitors(accountId) {
            location.href = `/monitors?account=${encodeURIComponent(accountId)}`;
        },
        async reloginAccount(phone) {
            await this.openAddModal();
            this.addForm.phone = phone;
            showNotification('请重新输入验证码完成账号登录', 'info');
        }
    },
    mounted() {
        this.loadAccounts();
    }
}).mount('#accounts-app');
