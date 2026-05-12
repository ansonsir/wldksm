import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 仅注册全局使用的图标（PageHeader动态组件 + Layout模板），其余局部导入
import {
  DataAnalysis, Aim, Clock, Setting, Files, List, Document,
  HomeFilled, UserFilled, ArrowDown, Lock, User, SwitchButton
} from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()

// 注册全局图标（用于 PageHeader <component :is="icon"> 和 Layout 模板）
const globalIcons = {
  DataAnalysis, Aim, Clock, Setting, Files, List, Document,
  HomeFilled, UserFilled, ArrowDown, Lock, User, SwitchButton
}
for (const [key, component] of Object.entries(globalIcons)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.use(pinia)
app.use(router)
app.mount('#app')
