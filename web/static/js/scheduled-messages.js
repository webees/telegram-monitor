const blankScheduledForm = () => ({
    account_id: '',
    message_type: 'text',
    message: '',
    ai_prompt: '',
    channel_id: '',
    schedule_mode: 'cron',
    schedule: '',
    interval_hours: 0,
    interval_minutes: 0,
    random_delay: 0,
    delete_after_send: false,
    max_executions: null
});

createVueApp({
    data() {
        return {
            accounts: [],
            messages: [],
            stats: {total_count: 0, paused_count: 0, total_executions: 0},
            loading: false,
            showModal: false,
            editingId: '',
            selectedMessage: null,
            form: blankScheduledForm()
        };
    },
    methods: {
        messageId(msg) {
            return msg.job_id || msg.id;
        },
        scheduleText(msg) {
            if (msg.schedule_mode === 'interval') {
                const [hours = '0', minutes = '0'] = String(msg.schedule || msg.cron || '').split(' ');
                const parts = [];
                if (Number(hours)) parts.push(`${Number(hours)}小时`);
                if (Number(minutes)) parts.push(`${Number(minutes)}分钟`);
                return `每隔 ${parts.join(' ') || '0分钟'}`;
            }
            return msg.schedule || msg.cron || '未设置';
        },
        async loadAccounts() {
            try {
                const data = await apiJson('/api/accounts');
                this.accounts = data.accounts || [];
            } catch {
                showNotification('加载账号失败', 'error');
            }
        },
        async loadMessages() {
            this.loading = true;
            try {
                const data = await apiJson('/api/scheduled-messages');
                this.messages = data.messages || [];
                this.stats = data.statistics || {
                    total_count: this.messages.length,
                    paused_count: this.messages.filter(msg => msg.active === false).length,
                    total_executions: this.messages.reduce((sum, msg) => sum + (msg.execution_count || 0), 0)
                };
            } catch (error) {
                showNotification(`加载计划任务失败: ${error.message}`, 'error');
            } finally {
                this.loading = false;
            }
        },
        openModal(msg = null) {
            this.editingId = msg ? this.messageId(msg) : '';
            this.form = msg ? this.formFromMessage(msg) : blankScheduledForm();
            this.showModal = true;
        },
        closeModal() {
            this.showModal = false;
            this.editingId = '';
            this.form = blankScheduledForm();
        },
        formFromMessage(msg) {
            const schedule = msg.schedule || msg.cron || '';
            const [hours = '0', minutes = '0'] = String(schedule).split(' ');
            return {
                account_id: msg.account_id || '',
                message_type: msg.use_ai ? 'ai' : 'text',
                message: msg.message || '',
                ai_prompt: msg.ai_prompt || '',
                channel_id: msg.channel_id || msg.target_id || '',
                schedule_mode: msg.schedule_mode || 'cron',
                schedule: (msg.schedule_mode || 'cron') === 'cron' ? schedule : '',
                interval_hours: Number(hours) || 0,
                interval_minutes: Number(minutes) || 0,
                random_delay: Number(msg.random_delay || msg.random_offset || 0),
                delete_after_send: Boolean(msg.delete_after_send || msg.delete_after_sending),
                max_executions: msg.max_executions || null
            };
        },
        validateForm() {
            if (!this.$refs.formEl.reportValidity()) return false;
            if (this.form.schedule_mode === 'interval') {
                const hours = Number(this.form.interval_hours || 0);
                const minutes = Number(this.form.interval_minutes || 0);
                if (hours === 0 && minutes === 0) {
                    showNotification('间隔时间不能为0', 'error');
                    return false;
                }
                if (minutes < 0 || minutes > 59) {
                    showNotification('分钟值必须在0-59之间', 'error');
                    return false;
                }
            }
            return true;
        },
        payload() {
            const useAi = this.form.message_type === 'ai';
            return {
                account_id: this.form.account_id,
                message: useAi ? '' : this.form.message,
                channel_id: this.form.channel_id,
                schedule_mode: this.form.schedule_mode,
                schedule: this.form.schedule_mode === 'cron'
                    ? this.form.schedule
                    : `${Number(this.form.interval_hours || 0)} ${Number(this.form.interval_minutes || 0)}`,
                use_ai: useAi,
                ai_prompt: useAi ? this.form.ai_prompt : '',
                random_delay: Number(this.form.random_delay || 0),
                delete_after_send: this.form.delete_after_send,
                max_executions: this.form.max_executions || null
            };
        },
        async saveMessage() {
            if (!this.validateForm()) return;
            try {
                const url = this.editingId
                    ? `/api/scheduled-messages/${encodeURIComponent(this.editingId)}`
                    : '/api/scheduled-messages';
                await apiSend(url, this.payload(), this.editingId ? 'PUT' : 'POST');
                this.closeModal();
                showNotification('计划任务保存成功', 'success');
                await this.loadMessages();
            } catch (error) {
                showNotification(`保存失败: ${error.message}`, 'error');
            }
        },
        async deleteMessage(msg) {
            const id = this.messageId(msg);
            if (!id || !confirm('确定要删除这条计划任务吗？')) return;
            try {
                await apiJson(`/api/scheduled-messages/${encodeURIComponent(id)}`, {method: 'DELETE'});
                showNotification('计划任务删除成功', 'success');
                await this.loadMessages();
            } catch (error) {
                showNotification(`删除失败: ${error.message}`, 'error');
            }
        },
        async toggleStatus(msg) {
            const id = this.messageId(msg);
            const active = msg.active === false;
            try {
                await apiSend(`/api/scheduled-messages/${encodeURIComponent(id)}/toggle`, {active}, 'PUT');
                showNotification(`计划任务已${active ? '启动' : '暂停'}`, 'success');
                await this.loadMessages();
            } catch (error) {
                showNotification(`状态更新失败: ${error.message}`, 'error');
            }
        },
        async showCronHelp() {
            try {
                const data = await apiJson('/api/cron-examples');
                if (data.success && data.examples) {
                    alert(data.examples.map(item => `${item.expression} -> ${item.description}`).join('\n'));
                    return;
                }
            } catch {
                // fall through to static examples
            }
            alert('0 9 * * * -> 每天9:00\n30 18 * * * -> 每天18:30\n0 */2 * * * -> 每2小时\n0 9 * * 1 -> 每周一9:00');
        },
        detailRows(msg) {
            return [
                {label: '消息ID', value: this.messageId(msg)},
                {label: '状态', value: msg.active !== false ? '运行中' : '已暂停'},
                {label: '账号', value: msg.account_id || '未设置'},
                {label: '目标', value: msg.channel_id || msg.target_id || '未设置'},
                {label: '调度表达式', value: this.scheduleText(msg)},
                {label: '消息类型', value: msg.use_ai ? 'AI生成' : '固定文本'},
                {label: '随机延时', value: `${msg.random_delay || msg.random_offset || 0} 秒`},
                {label: '发送后删除', value: msg.delete_after_send || msg.delete_after_sending ? '是' : '否'},
                {label: '最大执行次数', value: msg.max_executions || '无限制'},
                {label: '已执行次数', value: msg.execution_count || 0},
                {label: msg.use_ai ? 'AI提示词' : '消息内容', value: msg.use_ai ? (msg.ai_prompt || '无') : (msg.message || '无')}
            ];
        }
    },
    mounted() {
        this.loadAccounts();
        this.loadMessages();
    }
}).mount('#scheduled-app');
