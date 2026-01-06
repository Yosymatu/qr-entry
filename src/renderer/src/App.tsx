import { useState, useRef, useEffect } from 'react'

// 音声ファイルのインポート
import okSound from '../../assets/ok.wav'
import ngSound from '../../assets/ng.wav'

function App(): JSX.Element {
  // 音声の参照
  const okAudioRef = useRef<HTMLAudioElement | null>(null)
  const ngAudioRef = useRef<HTMLAudioElement | null>(null)

  // 音声要素の初期化
  useEffect(() => {
    okAudioRef.current = new Audio(okSound)
    ngAudioRef.current = new Audio(ngSound)
  }, [])
  const [status, setStatus] = useState<'idle' | 'ok' | 'ng' | 'error'>('idle')
  const [msg, setMsg] = useState('QRコードをスキャンしてください')
  const [eventName, setEventName] = useState('SampleEvent')
  const [minSeq, setMinSeq] = useState(100)
  const [checkEvent, setCheckEvent] = useState(true)
  const [checkSeq, setCheckSeq] = useState(true)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleKeyDown = async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const qrData = inputRef.current?.value || ''
      if (!qrData) return

      setMsg('判定中...')
      setStatus('idle')

      const result = await window.electronAPI.validateQr(
        qrData,
        eventName,
        minSeq,
        checkEvent,
        checkSeq
      )

      if (result.status === 'OK') {
        setStatus('ok')
        setMsg(result.msg)
        // OK音を再生
        okAudioRef.current?.play().catch(() => {})
      } else if (result.status === 'NG') {
        setStatus('ng')
        setMsg(result.msg)
        // NG音を再生
        ngAudioRef.current?.play().catch(() => {})
      } else {
        setStatus('error')
        setMsg(result.msg)
        // エラー時もNG音を再生
        ngAudioRef.current?.play().catch(() => {})
      }

      if (inputRef.current) {
        inputRef.current.value = ''
        inputRef.current.focus()
      }
    }
  }

  const handleExport = async () => {
    if (!confirm('入退場履歴をCSV形式で保存しますか？')) return
    const result = await window.api.exportData()
    if (result.status === 'success') {
      alert(result.message)
    } else if (result.status === 'error') {
      alert('エラー: ' + result.message)
    }
  }

  const handleClearDatabase = async () => {
    if (!confirm('データベースをクリアしますか？\nこの操作は元に戻せません。')) return
    const result = await window.electronAPI.clearDatabase()
    if (result.status === 'success') {
      alert(result.message)
      setStatus('idle')
      setMsg('QRコードをスキャンしてください')
    } else {
      alert('エラー: ' + result.message)
    }
  }

  const getStatusStyle = () => {
    switch (status) {
      case 'ok':
        return { bg: '#10b981', text: 'OK' }
      case 'ng':
        return { bg: '#ef4444', text: 'NG' }
      case 'error':
        return { bg: '#f59e0b', text: 'ERR' }
      default:
        return { bg: '#6b7280', text: '---' }
    }
  }

  const statusStyle = getStatusStyle()

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      padding: '20px'
    }}>
      {/* Header */}
      <header className="glass" style={{
        padding: '16px 24px',
        borderRadius: '16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px'
      }}>
        <h1 style={{
          fontSize: '20px',
          fontWeight: 600,
          color: '#fff',
          margin: 0,
          textShadow: '0 1px 2px rgba(0,0,0,0.1)'
        }}>
          QR Entry
        </h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={handleClearDatabase}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              fontWeight: 500,
              cursor: 'pointer',
              backgroundColor: 'rgba(239, 68, 68, 0.3)',
              color: '#fff',
              border: '1px solid rgba(239, 68, 68, 0.5)',
              borderRadius: '10px',
              backdropFilter: 'blur(10px)',
              transition: 'all 0.2s'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.5)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.3)'
            }}
          >
            DBクリア
          </button>
          <button
            onClick={handleExport}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              fontWeight: 500,
              cursor: 'pointer',
              backgroundColor: 'rgba(255, 255, 255, 0.25)',
              color: '#fff',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              borderRadius: '10px',
              backdropFilter: 'blur(10px)',
              transition: 'all 0.2s'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.35)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.25)'
            }}
          >
            CSV出力
          </button>
        </div>
      </header>

      {/* Main */}
      <main style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '24px'
      }}>
        {/* Status Card */}
        <div className="glass" style={{
          borderRadius: '24px',
          padding: '48px 64px',
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden'
        }}>
          {/* Status indicator glow */}
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '200px',
            height: '200px',
            borderRadius: '50%',
            background: status === 'ok' ? 'rgba(16, 185, 129, 0.3)' :
                       status === 'ng' ? 'rgba(239, 68, 68, 0.3)' :
                       status === 'error' ? 'rgba(245, 158, 11, 0.3)' :
                       'rgba(255, 255, 255, 0.1)',
            filter: 'blur(40px)',
            transition: 'background 0.3s'
          }} />
          <div style={{
            position: 'relative',
            zIndex: 1
          }}>
            <div style={{
              fontSize: '72px',
              fontWeight: 700,
              letterSpacing: '4px',
              color: '#fff',
              textShadow: '0 2px 10px rgba(0,0,0,0.2)'
            }}>
              {statusStyle.text}
            </div>
            <p style={{
              fontSize: '18px',
              marginTop: '12px',
              color: 'rgba(255, 255, 255, 0.9)'
            }}>
              {msg}
            </p>
          </div>
        </div>

        {/* Input */}
        <input
          type="text"
          ref={inputRef}
          onKeyDown={handleKeyDown}
          placeholder="QRコードをスキャン..."
          autoFocus
          style={{
            width: '100%',
            maxWidth: '360px',
            padding: '16px 20px',
            fontSize: '16px',
            border: '1px solid rgba(255, 255, 255, 0.3)',
            borderRadius: '14px',
            backgroundColor: 'rgba(255, 255, 255, 0.15)',
            backdropFilter: 'blur(20px)',
            color: '#fff',
            outline: 'none',
            textAlign: 'center',
            transition: 'all 0.2s',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.2)'
          }}
          onFocus={(e) => {
            e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.25)'
            e.target.style.borderColor = 'rgba(255, 255, 255, 0.5)'
          }}
          onBlur={(e) => {
            e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.15)'
            e.target.style.borderColor = 'rgba(255, 255, 255, 0.3)'
          }}
        />
      </main>

      {/* Settings */}
      <footer className="glass" style={{
        padding: '16px 24px',
        borderRadius: '16px',
        marginTop: '20px'
      }}>
        <div style={{
          display: 'flex',
          gap: '32px',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'center'
        }}>
          {/* Event */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              cursor: 'pointer',
              color: 'rgba(255, 255, 255, 0.8)',
              fontSize: '14px'
            }}>
              <input
                type="checkbox"
                checked={checkEvent}
                onChange={(e) => setCheckEvent(e.target.checked)}
                style={{
                  width: '18px',
                  height: '18px',
                  accentColor: '#fff'
                }}
              />
              イベント名
            </label>
            <input
              type="text"
              value={eventName}
              onChange={(e) => setEventName(e.target.value)}
              disabled={!checkEvent}
              style={{
                padding: '8px 12px',
                fontSize: '14px',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                width: '140px',
                backgroundColor: checkEvent ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.1)',
                color: checkEvent ? '#fff' : 'rgba(255, 255, 255, 0.5)',
                backdropFilter: 'blur(10px)',
                outline: 'none'
              }}
            />
          </div>

          {/* Seq */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              cursor: 'pointer',
              color: 'rgba(255, 255, 255, 0.8)',
              fontSize: '14px'
            }}>
              <input
                type="checkbox"
                checked={checkSeq}
                onChange={(e) => setCheckSeq(e.target.checked)}
                style={{
                  width: '18px',
                  height: '18px',
                  accentColor: '#fff'
                }}
              />
              連番下限
            </label>
            <input
              type="number"
              value={minSeq}
              onChange={(e) => setMinSeq(Number(e.target.value))}
              disabled={!checkSeq}
              style={{
                padding: '8px 12px',
                fontSize: '14px',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                width: '100px',
                backgroundColor: checkSeq ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.1)',
                color: checkSeq ? '#fff' : 'rgba(255, 255, 255, 0.5)',
                backdropFilter: 'blur(10px)',
                outline: 'none'
              }}
            />
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
