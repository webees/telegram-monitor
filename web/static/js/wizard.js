const isEnabled = value => value === true || value === 'true' || value === 'on' || value === 1 || value === '1';
const firstDefined = (...values) => values.find(value => value !== undefined && value !== null);

createVueApp({
    data() {
        return {
            sessionId: '',
            loading: true,
            saving: false,
            completed: false,
            completionMessage: '',
            editMode: false,
            editKey: '',
            editConfig: {},
            step: {fields: []},
            progress: {current: 1, total: 1, percentage: 0},
            values: {},
            errors: []
        };
    },
    computed: {
        stepTitle() {
            return this.step.title || '新建规则';
        },
        stepDescription() {
            return this.step.description || '';
        },
        visibleFields() {
            return (this.step.fields || []).filter(field => this.isVisible(field));
        },
        progressText() {
            return `步骤 ${this.progress.current || 1} / ${this.progress.total || 1}`;
        },
        canGoBack() {
            return (this.progress.current || 1) > 1 && !this.completed;
        },
        isFinishStep() {
            return this.step.type === 'review_config' || (this.progress.current || 1) >= (this.progress.total || 1);
        }
    },
    methods: {
        generateSessionId() {
            const prefix = `wizard_${Date.now()}_`;
            const cryptoApi = globalThis.crypto;
            if (cryptoApi && cryptoApi.randomUUID) return prefix + cryptoApi.randomUUID().replace(/-/g, '').slice(0, 9);
            if (cryptoApi && cryptoApi.getRandomValues) {
                const bytes = new Uint32Array(2);
                cryptoApi.getRandomValues(bytes);
                return prefix + bytes[0].toString(36) + bytes[1].toString(36);
            }
            return prefix + Math.random().toString(36).slice(2, 11);
        },
        parseMode() {
            const params = new URLSearchParams(location.search);
            this.editMode = params.get('edit') === 'true';
            this.editKey = params.get('key') || '';
            if (this.editMode) {
                try {
                    this.editConfig = JSON.parse(decodeURIComponent(params.get('config') || '{}'));
                    if (params.get('account_id')) this.editConfig.account_id = decodeURIComponent(params.get('account_id'));
                } catch {
                    this.editConfig = {};
                    this.errors = ['配置数据无效，请重新进入编辑页'];
                }
            }
            return params;
        },
        async start() {
            this.loading = true;
            const params = this.parseMode();
            const payload = {session_id: this.generateSessionId()};
            if (params.get('new') === 'true') payload.force_new = true;
            if (this.editMode && this.editKey) {
                payload.edit_mode = true;
                payload.edit_key = this.editKey;
                payload.edit_config = this.editConfig;
            }

            try {
                const data = await apiSend('/api/wizard/start', payload);
                if (data.success === false) throw new Error((data.errors || [data.message]).filter(Boolean).join('；'));
                this.sessionId = data.session_id || payload.session_id;
                this.applyStep(data);
                if (params.get('new') === 'true') history.replaceState({}, '', location.pathname);
            } catch (error) {
                this.errors = [error.message || '启动向导失败，请重试'];
            } finally {
                this.loading = false;
            }
        },
        applyStep(raw) {
            const data = raw.step_data || raw.next_step || raw;
            this.step = data.step || {fields: []};
            this.progress = data.progress || this.progress;
            this.errors = data.errors || [];
            this.seedValues(data.collected_data || {});
        },
        seedValues(collected) {
            const next = {...this.values, ...collected};
            for (const field of this.step.fields || []) {
                if (field.name in next) {
                    if (field.type === 'checkbox') next[field.name] = isEnabled(next[field.name]);
                    continue;
                }
                const value = firstDefined(field.value, this.editConfig[field.name], field.default, '');
                if (field.type === 'checkbox') next[field.name] = isEnabled(value);
                else if (field.type === 'range') next[field.name] = value || field.default || field.min || 0;
                else if (field.multiple) next[field.name] = Array.isArray(value) ? value : [];
                else next[field.name] = value;
            }
            this.values = next;
        },
        isVisible(field) {
            if (!field.conditional) return field.show !== false;
            return Object.entries(field.conditional).every(([name, expected]) => {
                const actual = this.values[name];
                return typeof expected === 'boolean' ? isEnabled(actual) === expected : actual === expected;
            });
        },
        payload() {
            const data = {};
            for (const field of this.step.fields || []) {
                if (field.type === 'section_header' || field.type === 'readonly') continue;
                if (field.type === 'checkbox') data[field.name] = isEnabled(this.values[field.name]);
                else data[field.name] = firstDefined(this.values[field.name], '');
            }
            return data;
        },
        validateLocal(data) {
            if (!this.$refs.formEl.reportValidity()) return false;
            if (this.step.type === 'button_config'
                && data.monitor_subtype === 'button_only'
                && data.mode === 'manual'
                && !String(data.button_keyword || '').trim()) {
                this.errors = ['手动模式下必须填写按钮关键词'];
                return false;
            }
            return true;
        },
        async submit() {
            const data = this.payload();
            this.errors = [];
            if (!this.validateLocal(data)) return;

            this.saving = true;
            try {
                const result = await apiSend('/api/wizard/step', {session_id: this.sessionId, ...data});
                if (result.success) {
                    if (result.next_step) this.applyStep(result.next_step);
                    else {
                        this.completed = true;
                        this.completionMessage = result.message || '规则创建成功';
                        this.progress = {...this.progress, percentage: 100};
                    }
                    return;
                }
                this.errors = result.errors || [result.message || result.detail || '提交失败，请检查输入'];
                if (result.step_data) this.applyStep(result.step_data);
            } catch (error) {
                this.errors = [error.message || '提交失败，请重试'];
            } finally {
                this.saving = false;
            }
        },
        async previous() {
            if (!this.canGoBack || this.saving) return;
            this.saving = true;
            try {
                const result = await apiSend('/api/wizard/previous', {session_id: this.sessionId});
                if (result.success) this.applyStep(result.step_data);
                else this.errors = result.errors || ['无法返回上一步'];
            } catch (error) {
                this.errors = [error.message || '返回上一步失败'];
            } finally {
                this.saving = false;
            }
        },
        cancel() {
            if (confirm('确定要取消新建规则吗？已填写的信息将丢失。')) location.href = '/monitors';
        },
        createNew() {
            location.href = `${location.pathname}?new=true&timestamp=${Date.now()}`;
        }
    },
    mounted() {
        this.start();
    }
}).mount('#wizard-app');
