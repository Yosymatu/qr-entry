import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import { copyFileSync, mkdirSync, existsSync } from 'fs'

// validator.pyをビルド出力にコピーするプラグイン
function copyValidatorPlugin() {
  return {
    name: 'copy-validator',
    closeBundle() {
      const srcPath = resolve(__dirname, 'src/main/validator.py')
      const destDir = resolve(__dirname, 'out/main')
      const destPath = resolve(destDir, 'validator.py')

      if (!existsSync(destDir)) {
        mkdirSync(destDir, { recursive: true })
      }

      if (existsSync(srcPath)) {
        copyFileSync(srcPath, destPath)
        console.log('validator.py copied to out/main/')
      }
    }
  }
}

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin(), copyValidatorPlugin()]
  },
  preload: {
    plugins: [externalizeDepsPlugin()]
  },
  renderer: {
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src')
      }
    },
    plugins: [react()]
  }
})