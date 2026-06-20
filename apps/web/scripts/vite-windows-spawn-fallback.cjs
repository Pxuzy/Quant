const childProcess = require('node:child_process');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');

const originalExec = childProcess.exec;

function createCompletedChildProcess() {
  const child = new EventEmitter();
  child.stdin = new PassThrough();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.pid = 0;
  child.killed = false;
  child.exitCode = 0;
  child.signalCode = null;
  child.kill = () => false;

  process.nextTick(() => {
    child.stdout.end();
    child.stderr.end();
    child.emit('exit', 0, null);
    child.emit('close', 0, null);
  });

  return child;
}

childProcess.exec = function execWithWindowsNetUseFallback(command, options, callback) {
  const normalizedCommand = typeof command === 'string' ? command.trim().toLowerCase() : '';
  const callbackArg = typeof options === 'function' ? options : callback;

  if (process.platform === 'win32' && normalizedCommand === 'net use') {
    if (typeof callbackArg === 'function') {
      process.nextTick(() => callbackArg(null, '', ''));
    }
    return createCompletedChildProcess();
  }

  return originalExec.apply(this, arguments);
};
