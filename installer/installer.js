import archivePath from "../dist/FC_SERV_Python_3.2.6.zip" with { type: "file" };
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

function psLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

if (process.env.FATURA_INSTALLER_VALIDATE === "1") {
  const bytes = new Uint8Array(await Bun.file(archivePath).arrayBuffer());
  if (bytes.length < 1000 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
    throw new Error("O pacote incorporado ao instalador é inválido.");
  }
  console.log(`Pacote incorporado validado: ${bytes.length} bytes.`);
  process.exit(0);
}

if (process.platform !== "win32") {
  console.error("Este instalador deve ser executado no Windows 64 bits.");
  process.exit(1);
}

const base = process.env.LOCALAPPDATA || homedir();
const installDir = join(base, "FC SERV", "Aplicativo");
const zipPath = join(base, "FC SERV", "instalacao.zip");
mkdirSync(installDir, { recursive: true });
writeFileSync(zipPath, Buffer.from(await Bun.file(archivePath).arrayBuffer()));

console.log("Preparando o FC SERV...");
const expand = Bun.spawnSync({
  cmd: [
    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
    `$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='Stop'; Expand-Archive -LiteralPath ${psLiteral(zipPath)} -DestinationPath ${psLiteral(installDir)} -Force`
  ],
  stdout: "inherit",
  stderr: "inherit",
});
if (expand.exitCode !== 0 || !existsSync(join(installDir, "INSTALAR_E_INICIAR.bat"))) {
  console.error("Não foi possível preparar os arquivos do aplicativo.");
  console.log("Pressione Enter para fechar.");
  await new Promise(resolve => process.stdin.once("data", resolve));
  process.exit(2);
}

const shortcutScript = [
  "$desktop = [Environment]::GetFolderPath('Desktop')",
  "$shell = New-Object -ComObject WScript.Shell",
  `$shortcut = $shell.CreateShortcut((Join-Path $desktop 'FC SERV.lnk'))`,
  `$shortcut.TargetPath = ${psLiteral(join(installDir, "INICIAR.bat"))}`,
  `$shortcut.WorkingDirectory = ${psLiteral(installDir)}`,
  `$shortcut.IconLocation = ${psLiteral(join(installDir, "app", "static", "fc-serv-logo.ico"))}`,
  "$shortcut.Description = 'FC SERV'",
  "$shortcut.Save()",
  `$serverShortcut = $shell.CreateShortcut((Join-Path $desktop 'FC SERV - Servidor.lnk'))`,
  `$serverShortcut.TargetPath = ${psLiteral(join(installDir, "INICIAR_SERVIDOR.bat"))}`,
  `$serverShortcut.WorkingDirectory = ${psLiteral(installDir)}`,
  `$serverShortcut.IconLocation = ${psLiteral(join(installDir, "app", "static", "fc-serv-logo.ico"))}`,
  "$serverShortcut.Description = 'FC SERV - Servidor central'",
  "$serverShortcut.Save()",
].join("; ");
Bun.spawnSync({
  cmd: ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", shortcutScript],
  stdout: "ignore",
  stderr: "ignore",
});

console.log("Arquivos preparados com sucesso.");
console.log("A janela permanecera aberta para mostrar todas as etapas da instalacao.");
const commandLine = `cd /d "${installDir}" && call "INSTALAR_E_INICIAR.bat"`;
const start = Bun.spawn({
  cmd: ["cmd.exe", "/d", "/k", commandLine],
  cwd: installDir,
  stdout: "inherit",
  stderr: "inherit",
});
const exitCode = await start.exited;
process.exit(exitCode);
