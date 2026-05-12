<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>用户管理</span>
        <el-button type="primary" @click="showCreateUser = true">创建用户</el-button>
      </div>
    </template>

    <el-table :data="userList" style="width: 100%">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="150" />
      <el-table-column prop="email" label="邮箱" width="200" />
      <el-table-column label="管理员" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">
            {{ row.is_admin ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="TOTP" width="80">
        <template #default="{ row }">
          <el-tag :type="row.totp_enabled ? 'success' : 'warning'" size="small">
            {{ row.totp_enabled ? '已启用' : '未启用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_login" label="最后登录" width="180" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '正常' : '锁定' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="handleEditUser(row)">编辑</el-button>
          <el-button size="small" @click="handleResetPassword(row)">重置密码</el-button>
          <el-button size="small" type="danger" @click="handleDeleteUser(row)" :disabled="row.id === currentUserId">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建用户对话框 -->
    <el-dialog v-model="showCreateUser" title="创建用户" width="500px">
      <el-form :model="createUserForm" label-width="120px">
        <el-form-item label="用户名">
          <el-input v-model="createUserForm.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createUserForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="createUserForm.email" />
        </el-form-item>
        <el-form-item label="管理员">
          <el-switch v-model="createUserForm.is_admin" />
        </el-form-item>
        <el-form-item label="启用TOTP认证">
          <el-switch v-model="createUserForm.enable_totp" />
          <div style="color: #909399; font-size: 12px; margin-top: 5px">
            启用后，用户首次登录时需要设置TOTP双因素认证
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleCreateUser">创建</el-button>
          <el-button @click="showCreateUser = false">取消</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>

    <!-- 编辑用户对话框 -->
    <el-dialog v-model="showEditUser" title="编辑用户" width="600px">
      <el-form :model="editUserForm" label-width="120px">
        <el-form-item label="用户名">
          <el-input v-model="editUserForm.username" disabled />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editUserForm.email" />
        </el-form-item>
        <el-form-item label="管理员">
          <el-switch v-model="editUserForm.is_admin" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editUserForm.is_active" active-text="正常" inactive-text="锁定" />
        </el-form-item>

        <el-divider>双因素认证（TOTP）管理</el-divider>
        <el-form-item label="TOTP状态">
          <el-tag v-if="editUserForm.totp_enabled" type="success" size="large">已启用</el-tag>
          <el-tag v-else type="info" size="large">未启用</el-tag>
        </el-form-item>
        <el-form-item label="TOTP操作">
          <el-button v-if="!editUserForm.totp_enabled" type="success" @click="handleEnableTotp">
            启用TOTP
          </el-button>
          <el-button v-if="editUserForm.totp_enabled" type="warning" @click="handleDisableTotpForUser">
            禁用TOTP
          </el-button>
          <el-button v-if="editUserForm.totp_enabled" type="danger" @click="handleResetTotp">
            重置TOTP
          </el-button>
        </el-form-item>
        <el-form-item v-if="editUserForm.totp_enabled">
          <el-alert
            title="重置TOTP后，用户需要重新扫码绑定"
            type="warning"
            :closable="false"
            show-icon
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleUpdateUser">保存</el-button>
          <el-button @click="showEditUser = false">取消</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="showResetPassword" title="重置密码" width="400px">
      <el-form :model="resetPasswordForm" label-width="100px">
        <el-form-item label="新密码">
          <el-input v-model="resetPasswordForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="confirmResetPassword">确认重置</el-button>
          <el-button @click="showResetPassword = false">取消</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const userStr = localStorage.getItem('user_info')
const currentUser = userStr ? JSON.parse(userStr) : {}
const currentUserId = computed(() => currentUser.id)

const userList = ref([])
const showCreateUser = ref(false)
const showEditUser = ref(false)
const showResetPassword = ref(false)
const selectedUserId = ref(null)

const createUserForm = reactive({
  username: '',
  password: '',
  email: '',
  is_admin: false,
  enable_totp: false
})

const editUserForm = reactive({
  id: null,
  username: '',
  email: '',
  is_admin: false,
  is_active: true,
  totp_enabled: false
})

const resetPasswordForm = reactive({ password: '' })

const loadUserList = async () => {
  try {
    const res = await api.get('/api/v1/auth/users')
    if (res.success) userList.value = res.data
  } catch (e) { /* handled by interceptor */ }
}

const handleCreateUser = async () => {
  if (!createUserForm.username || !createUserForm.password) {
    ElMessage.error('用户名和密码不能为空')
    return
  }
  try {
    const res = await api.post('/api/v1/auth/users', {
      username: createUserForm.username,
      password: createUserForm.password,
      email: createUserForm.email,
      is_admin: createUserForm.is_admin,
      enable_totp: createUserForm.enable_totp
    })
    if (res.success) {
      ElMessage.success('用户创建成功')
      showCreateUser.value = false
      Object.assign(createUserForm, { username: '', password: '', email: '', is_admin: false, enable_totp: false })
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '创建失败')
  }
}

const handleEditUser = (user) => {
  editUserForm.id = user.id
  editUserForm.username = user.username
  editUserForm.email = user.email || ''
  editUserForm.is_admin = user.is_admin
  editUserForm.is_active = user.is_active
  editUserForm.totp_enabled = user.totp_enabled
  showEditUser.value = true
}

const handleEnableTotp = async () => {
  try {
    const res = await api.post(`/api/v1/auth/users/${editUserForm.id}/enable-totp`)
    if (res.success) {
      ElMessage.success('TOTP已启用')
      editUserForm.totp_enabled = true
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '启用失败')
  }
}

const handleDisableTotpForUser = async () => {
  try {
    const res = await api.post(`/api/v1/auth/users/${editUserForm.id}/disable-totp`)
    if (res.success) {
      ElMessage.success('TOTP已禁用')
      editUserForm.totp_enabled = false
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '禁用失败')
  }
}

const handleResetTotp = async () => {
  try {
    await ElMessageBox.confirm(
      '重置后，用户需要重新扫码绑定TOTP。是否继续？',
      '确认重置',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await api.post(`/api/v1/auth/users/${editUserForm.id}/reset-totp`)
    if (res.success) {
      ElMessage.success('TOTP已重置，用户需要重新扫码绑定')
      loadUserList()
      showEditUser.value = false
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.error || '重置失败')
    }
  }
}

const handleUpdateUser = async () => {
  if (!editUserForm.username) {
    ElMessage.error('用户名不能为空')
    return
  }
  try {
    const res = await api.put(`/api/v1/auth/users/${editUserForm.id}`, {
      username: editUserForm.username,
      email: editUserForm.email,
      is_admin: editUserForm.is_admin,
      is_active: editUserForm.is_active
    })
    if (res.success) {
      ElMessage.success('用户信息更新成功')
      showEditUser.value = false
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '更新失败')
  }
}

const handleResetPassword = (user) => {
  selectedUserId.value = user.id
  resetPasswordForm.password = ''
  showResetPassword.value = true
}

const confirmResetPassword = async () => {
  if (!resetPasswordForm.password) {
    ElMessage.error('密码不能为空')
    return
  }
  try {
    const res = await api.post(`/api/v1/auth/users/${selectedUserId.value}/reset-password`, {
      password: resetPasswordForm.password
    })
    if (res.success) {
      ElMessage.success('密码重置成功')
      showResetPassword.value = false
      resetPasswordForm.password = ''
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '重置失败')
  }
}

const handleDeleteUser = async (user) => {
  try {
    await ElMessageBox.confirm(`确定要删除用户 "${user.username}" 吗？`, '提示', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
    const res = await api.delete(`/api/v1/auth/users/${user.id}`)
    if (res.success) {
      ElMessage.success('用户已删除')
      loadUserList()
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.error || '删除失败')
    }
  }
}

onMounted(loadUserList)
</script>
