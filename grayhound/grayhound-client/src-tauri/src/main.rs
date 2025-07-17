// src-tauri/src/main.rs
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

// use tauri::{Emitter, Window};
// use tauri_plugin_shell::ShellExt;

// #[tauri::command]
// async fn run_script(
//     window: Window,
//     command: String,
//     args: Vec<String>,
// ) -> Result<(), String> {
//     let shell = window.shell();
    
//     // ✅ 1. tauri.conf.json에 정의한 식별자로 사이드카를 호출
//     let sidecar = shell.sidecar("run-python-sidecar")
//         .map_err(|e| format!("Failed to create sidecar: {}", e))?;

//     // ✅ 2. 전달할 인자들을 구성
//     let mut full_args = vec![command];
//     full_args.extend(args);

//     // ✅ 3. 사이드카를 실행
//     let (mut rx, _child) = sidecar
//         .args(&full_args)
//         .spawn()
//         .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

//     // 이벤트 처리 로직        
//     while let Some(event) = rx.recv().await {
//         match event {
//             // 표준 출력(stdout)은 'script-output' 이벤트로 전달
//             tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
//                 window.emit("script-output", &line).unwrap();
//             }
//             // 표준 에러(stderr)는 'script-error' 이벤트로 전달
//             tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
//                 window.emit("script-error", &line).unwrap();
//             }
//             tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
//                 // 프로세스가 0이 아닌 코드로 종료되면 에러를 발생시킴
//                 if payload.code != Some(0) {
//                     let msg = format!("Script terminated with non-zero exit code: {:?}", payload.code);
//                     window.emit("script-error", &msg).unwrap();
//                 }
//             }
//             _ => {} // 다른 이벤트는 무시
//         }
//     }

//     Ok(())
// }

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}