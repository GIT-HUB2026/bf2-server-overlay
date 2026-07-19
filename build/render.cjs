// headless render of gen.html — usage:
//   electron render.cjs sheet <out.png>
//   electron render.cjs <conceptNumber> <out.png> [size]
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path');

const mode = process.argv[2];
const out = process.argv[3];
const size = parseInt(process.argv[4] || '1024', 10);
const sheet = mode === 'sheet';
const W = sheet ? 1130 : size, H = sheet ? 560 : size;

app.commandLine.appendSwitch('force-color-profile', 'srgb');
app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: W, height: H, show: false, frame: false,
    transparent: !sheet, webPreferences: { offscreen: true } });
  const query = sheet ? {} : { c: String(mode), size: String(size) };
  await win.loadFile(path.join(__dirname, 'logo-explore', 'gen.html'), { query });
  await new Promise(r => setTimeout(r, 900));
  const img = await win.webContents.capturePage();
  fs.writeFileSync(out, img.toPNG());
  console.log('written', out);
  app.quit();
});
