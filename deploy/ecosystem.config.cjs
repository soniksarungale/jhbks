// pm2 process for the WindSight API. nginx serves the built frontend.
//   pm2 start deploy/ecosystem.config.cjs && pm2 save
const path = require('path')

module.exports = {
  apps: [
    {
      name: 'windsight',
      cwd: path.join(__dirname, '..', 'backend'),
      script: '.venv/bin/uvicorn',
      args: 'app.main:app --host 127.0.0.1 --port 4600 --proxy-headers --no-access-log',
      interpreter: 'none',
      autorestart: true,
      max_memory_restart: '400M',
      restart_delay: 3000,
      out_file: path.join(__dirname, '..', 'logs', 'out.log'),
      error_file: path.join(__dirname, '..', 'logs', 'error.log'),
      merge_logs: true,
      time: true,
      env: { WINDSIGHT_DB_PATH: 'data/windsight.db' },
    },
  ],
}
