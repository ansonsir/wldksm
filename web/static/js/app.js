const { createApp, ref, reactive, onMounted, onUnmounted, computed } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

// API 基础配置
const api = axios.create({
    baseURL: '',
    timeout: 30000,
});

// 请求拦截器
api.interceptors.response.use(
    response => response.data,
    error => {
        const msg = error.response?.data?.message || error.message || '请求失败';
        ElMessage.error(msg);
        return Promise.reject(error);
    }
);

const app = createApp({
    setup() {
        // 页面路由
        const currentPage = ref('dashboard');
        const activeMenu = ref('dashboard');
        const systemStatus = ref('online');

        // 统计数据
        const stats = ref({});
        const recentRecords = ref([]);

        // 扫描任务
        const scanForm = reactive({
            ip_ranges: '',
            ports: '',
            exclude_ips: '',
            max_workers: 32,
        });
        const scanDefaultsLoaded = ref(false);
        const scanning = ref(false);
        const scanCompleted = ref(false);
        const currentTaskId = ref('');
        const scanProgress = ref(0);
        const scanMessage = ref('');
        const scanLogs = ref([]);
        let scanStatusTimer = null;

        // 扫描历史
        const historyRecords = ref([]);
        const historyDetailVisible = ref(false);
        const historyDetail = ref(null);

        // 报告管理
        const reportRecords = ref([]);
        const sendMailVisible = ref(false);
        const selectedReport = ref(null);
        const mailForm = reactive({
            recipients: '',
            subject: '',
            body: '',
        });
        const sendingMail = ref(false);

        // 模板管理
        const templates = ref([]);

        // 系统配置
        const configForm = reactive({
            ip_range_file: '',
            ports_file: '',
            exclude_ips_file: '',
            max_workers: 32,
            ulimit: 32768,
            timeout: 300,
        });
        const mailConfigForm = reactive({
            smtp_server: '',
            smtp_port: 587,
            smtp_user: '',
            smtp_password: '',
            smtp_ssl: true,
            default_sender: '',
            default_recipients: '',
        });

        // ==================== 辅助函数 ====================

        const statusType = (status) => {
            const map = {
                'completed': 'success',
                'running': 'primary',
                'failed': 'danger',
                'cancelled': 'warning',
            };
            return map[status] || 'info';
        };

        const statusText = (status) => {
            const map = {
                'completed': '完成',
                'running': '运行中',
                'failed': '失败',
                'cancelled': '已取消',
            };
            return map[status] || status;
        };

        const scanProgressStatus = computed(() => {
            if (scanCompleted.value) return 'success';
            return '';
        });

        // ==================== 页面导航 ====================

        const handleMenuSelect = (index) => {
            currentPage.value = index;
            activeMenu.value = index;

            if (index === 'scan') loadScanDefaults();
            if (index === 'history') loadHistory();
            if (index === 'reports') loadReports();
            if (index === 'templates') loadTemplates();
            if (index === 'settings') loadSettings();
            if (index === 'dashboard') loadDashboard();
        };

        // ==================== 数据加载 ====================

        const loadDashboard = async () => {
            try {
                const res = await api.get('/api/stats');
                if (res.success) stats.value = res.data;

                const historyRes = await api.get('/api/scan/history?limit=5');
                if (historyRes.success) recentRecords.value = historyRes.data;
            } catch (e) {
                systemStatus.value = 'offline';
            }
        };

        const loadHistory = async () => {
            try {
                const res = await api.get('/api/scan/history?limit=100');
                if (res.success) historyRecords.value = res.data;
            } catch (e) {}
        };

        const loadReports = async () => {
            try {
                const res = await api.get('/api/reports');
                if (res.success) {
                    reportRecords.value = res.data || [];
                }
            } catch (e) {}
        };

        const loadTemplates = async () => {
            try {
                const res = await api.get('/api/templates');
                if (res.success) templates.value = res.data;
            } catch (e) {}
        };

        const loadSettings = async () => {
            try {
                const configRes = await api.get('/api/config');
                if (configRes.success) {
                    Object.assign(configForm, configRes.data);
                }
                const mailRes = await api.get('/api/mail/config');
                if (mailRes.success && mailRes.data) {
                    Object.assign(mailConfigForm, mailRes.data);
                }
            } catch (e) {}
        };

        // ==================== 扫描任务 ====================

        const loadScanDefaults = async () => {
            if (scanDefaultsLoaded.value) return;
            try {
                const res = await api.get('/api/scan/defaults');
                if (res.success) {
                    const data = res.data;
                    if (!scanForm.ip_ranges && data.ip_ranges) {
                        scanForm.ip_ranges = data.ip_ranges;
                    }
                    if (!scanForm.ports && data.ports) {
                        scanForm.ports = data.ports;
                    }
                    if (!scanForm.exclude_ips && data.exclude_ips) {
                        scanForm.exclude_ips = data.exclude_ips;
                    }
                    if (data.max_workers) {
                        scanForm.max_workers = data.max_workers;
                    }
                    scanDefaultsLoaded.value = true;
                }
            } catch (e) {
                console.error('加载默认扫描配置失败:', e);
            }
        };

        const formatTime = (seconds) => {
            if (!seconds || seconds < 0) return '0秒';
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            if (mins > 0) return `${mins}分${secs}秒`;
            return `${secs}秒`;
        };

        const startScan = async () => {
            scanning.value = true;
            scanCompleted.value = false;
            scanProgress.value = 0;
            scanMessage.value = '正在启动扫描...';
            scanLogs.value = [];

            try {
                const res = await api.post('/api/scan/start', {
                    ip_ranges: scanForm.ip_ranges,
                    ports: scanForm.ports,
                    exclude_ips: scanForm.exclude_ips,
                    max_workers: scanForm.max_workers,
                });

                if (res.success) {
                    currentTaskId.value = res.data.task_id;
                    ElMessage.success('扫描任务已启动');
                    startStatusPolling();
                } else {
                    ElMessage.error(res.message);
                    scanning.value = false;
                }
            } catch (e) {
                scanning.value = false;
            }
        };

        const stopScan = async () => {
            if (!currentTaskId.value) return;

            try {
                await api.post(`/api/scan/stop/${currentTaskId.value}`);
                ElMessage.info('已发送停止请求');
            } catch (e) {}
        };

        const startStatusPolling = () => {
            if (scanStatusTimer) clearInterval(scanStatusTimer);

            scanStatusTimer = setInterval(async () => {
                if (!currentTaskId.value) {
                    clearInterval(scanStatusTimer);
                    return;
                }

                try {
                    const res = await api.get(`/api/scan/status/${currentTaskId.value}`);
                    if (res.success) {
                        const data = res.data;
                        scanProgress.value = Math.round((data.progress / data.total) * 100) || 0;

                        // 构建详细进度信息
                        let msgParts = [data.message];
                        if (data.found_hosts > 0) {
                            msgParts.push(`累计发现 ${data.found_hosts} 台主机`);
                        }
                        if (data.open_ports > 0) {
                            msgParts.push(`${data.open_ports} 个开放端口`);
                        }
                        if (data.elapsed_time > 0) {
                            msgParts.push(`已用时间: ${formatTime(data.elapsed_time)}`);
                        }
                        if (data.estimated_remaining > 0) {
                            msgParts.push(`预计剩余: ${formatTime(data.estimated_remaining)}`);
                        }
                        scanMessage.value = msgParts.join(' | ');

                        if (data.status === 'completed') {
                            scanning.value = false;
                            scanCompleted.value = true;
                            clearInterval(scanStatusTimer);
                            ElMessage.success('扫描完成！');
                            loadReports();
                            loadHistory();
                        } else if (data.status === 'failed' || data.status === 'cancelled') {
                            scanning.value = false;
                            clearInterval(scanStatusTimer);
                            ElMessage.warning(data.message);
                        }
                    }
                } catch (e) {
                    // 继续轮询
                }
            }, 2000);
        };

        // ==================== 历史详情 ====================

        const viewHistoryDetail = async (row) => {
            try {
                const res = await api.get(`/api/scan/history/${row.id}`);
                if (res.success) {
                    historyDetail.value = res.data;
                    historyDetailVisible.value = true;
                }
            } catch (e) {}
        };

        // ==================== 报告下载 ====================

        const downloadReport = (path) => {
            window.open(`/api/reports/download?path=${encodeURIComponent(path)}`, '_blank');
        };

        // ==================== 邮件发送 ====================

        const openSendMailDialog = (report) => {
            selectedReport.value = report;
            mailForm.recipients = mailConfigForm.default_recipients || '';
            mailForm.subject = `网络端口扫描报告 - ${report.name}`;
            mailForm.body = `请查收附件中的网络端口扫描报告。\n\n报告文件: ${report.name}`;
            sendMailVisible.value = true;
        };

        const sendReportMail = async () => {
            if (!mailForm.recipients.trim()) {
                ElMessage.warning('请输入收件人');
                return;
            }

            sendingMail.value = true;
            try {
                const res = await api.post('/api/reports/send', {
                    report_path: selectedReport.value.path,
                    recipients: mailForm.recipients,
                    subject: mailForm.subject,
                    body: mailForm.body,
                });

                if (res.success) {
                    ElMessage.success('邮件发送成功');
                    sendMailVisible.value = false;
                } else {
                    ElMessage.error(res.message);
                }
            } catch (e) {}
            sendingMail.value = false;
        };

        // ==================== 模板上传 ====================

        const handleUploadSuccess = () => {
            ElMessage.success('模板上传成功');
            loadTemplates();
        };

        const handleUploadError = (err) => {
            ElMessage.error('上传失败: ' + (err.message || '未知错误'));
        };

        // ==================== 配置管理 ====================

        const saveConfig = async () => {
            try {
                const res = await api.post('/api/config', configForm);
                if (res.success) {
                    ElMessage.success('配置已保存');
                }
            } catch (e) {}
        };

        const saveMailConfig = async () => {
            try {
                const res = await api.post('/api/mail/config', mailConfigForm);
                if (res.success) {
                    ElMessage.success('邮件配置已保存');
                }
            } catch (e) {}
        };

        const testMailConfig = async () => {
            try {
                const res = await api.post('/api/mail/test', mailConfigForm);
                if (res.success) {
                    ElMessage.success(res.message);
                } else {
                    ElMessage.error(res.message);
                }
            } catch (e) {}
        };

        // ==================== 生命周期 ====================

        onMounted(() => {
            loadDashboard();
        });

        onUnmounted(() => {
            if (scanStatusTimer) clearInterval(scanStatusTimer);
        });

        return {
            currentPage,
            activeMenu,
            systemStatus,
            stats,
            recentRecords,
            scanForm,
            scanning,
            scanCompleted,
            currentTaskId,
            scanProgress,
            scanMessage,
            scanLogs,
            scanProgressStatus,
            formatTime,
            historyRecords,
            historyDetailVisible,
            historyDetail,
            reportRecords,
            sendMailVisible,
            selectedReport,
            mailForm,
            sendingMail,
            templates,
            configForm,
            mailConfigForm,
            statusType,
            statusText,
            handleMenuSelect,
            loadScanDefaults,
            startScan,
            stopScan,
            viewHistoryDetail,
            downloadReport,
            openSendMailDialog,
            sendReportMail,
            handleUploadSuccess,
            handleUploadError,
            saveConfig,
            saveMailConfig,
            testMailConfig,
        };
    }
});

// 注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

app.use(ElementPlus);
app.mount('#app');
