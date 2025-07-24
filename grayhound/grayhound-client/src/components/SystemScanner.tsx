// src/components/SystemScanner.tsx
import { useState, useEffect, useRef } from 'react';
import './SystemScanner.scss';

// 타입 정의
interface ScanResult {
  id: string;
  name: string;
  masked_name: string;
  reason: string;
  risk_score: number;
  path: string;
  pid: number | null;
  type: 'program' | 'process';
  clean: boolean; // 클라이언트에서 정리 여부를 관리하기 위한 상태
}

interface CleanupResult {
  name: string;
  masked_name: string;
  guide_masked_name?: string; // 가이드 메시지에 쓰일 마스킹된 이름
  path: string;
  status: 'success' | 'failure' | 'phase_a_failed'| 'manual_required' | 'ui_opened' | 'still_exists';
  message: string;
  ui_opened?: boolean;
  force_failed?: boolean;
  phase_completed?: string;
  automated?: boolean;  // UI 자동화 성공 여부
  timeout?: boolean;    // 타임아웃 발생 여부
}

interface PhaseStatus {
  [key: string]: {
    phase_a?: 'pending' | 'success' | 'failed';
    phase_b?: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped';
    phase_c?: 'pending' | 'success' | 'failed' | 'skipped';
    removal_verified?: boolean;
    ui_automation?: 'success' | 'failed' | 'timeout';
  };
}

interface BackendMessage {
  type: string;
  data: any;
}

interface SystemScannerProps {
  setCurrentView: (view: string) => void;
  language: string;
}

// 경고 메시지 다국어 지원
const warnings = {
  en: "⚠️ IMPORTANT: This can delete important files! If you remove the wrong program, your system or other programs may not work properly. The creators are not responsible for any problems that may occur. Do you really want to proceed?",
  ko: "⚠️ 중요: 중요한 파일을 삭제할 수 있습니다! 잘못된 프로그램을 제거하면 시스템이나 다른 프로그램이 제대로 작동하지 않을 수 있습니다. 발생할 수 있는 모든 문제에 대해 제작자는 책임지지 않습니다. 정말로 진행하시겠습니까?",
  ja: "⚠️ 重要：これにより重要なファイルが削除される可能性があります！間違ったプログラムを削除すると、システムや他のプログラムが正常に動作しなくなる可能性があります。発生する可能性のある問題について、作成者は責任を負いません。本当に続行しますか？",
  zh: "⚠️ 重要：这可能会删除重要文件！如果删除错误的程序，您的系统或其他程序可能无法正常工作。对于可能出现的任何问题，创作者概不负责。您真的要继续吗？",
};

// AI 기반 검출 관련 법적 면책 경고
const legalDisclaimer = {
  en: "⚠️ LEGAL NOTICE: The bloatware detection is based on AI analysis and community reports, which may not be 100% accurate. The actual program names are masked for legal protection. By revealing the actual names through user interaction, you acknowledge that: 1) The identification may be incorrect, 2) Any actions taken based on this information are at your own risk, 3) The developers are not responsible for any consequences. The decision to remove any software is entirely yours.",
  ko: "⚠️ 법적 고지: 블로트웨어 검출은 AI 분석과 커뮤니티 보고를 기반으로 하며, 100% 정확하지 않을 수 있습니다. 실제 프로그램 이름은 법적 보호를 위해 마스킹되어 있습니다. 사용자 상호작용을 통해 실제 이름을 확인함으로써, 귀하는 다음을 인정합니다: 1) 식별이 부정확할 수 있음, 2) 이 정보를 기반으로 한 모든 행동은 본인 책임임, 3) 개발자는 어떠한 결과에도 책임지지 않음. 소프트웨어 제거 결정은 전적으로 귀하의 책임입니다.",
  ja: "⚠️ 法的通知：ブロートウェアの検出はAI分析とコミュニティレポートに基づいており、100％正確ではない可能性があります。実際のプログラム名は法的保護のためマスクされています。ユーザー操作により実際の名前を確認することで、以下を承認します：1）識別が不正確である可能性、2）この情報に基づくすべての行動は自己責任、3）開発者はいかなる結果にも責任を負いません。ソフトウェアの削除決定は完全にあなたの責任です。",
  zh: "⚠️ 法律声明：膨胀软件检测基于AI分析和社区报告，可能不是100%准确。实际程序名称因法律保护而被屏蔽。通过用户交互显示实际名称，您承认：1）识别可能不准确，2）基于此信息采取的任何行动均由您自行承担风险，3）开发人员对任何后果不负责任。删除任何软件的决定完全由您负责。"
};

// 가이드 텍스트 다국어 지원
const guideTexts = {
  en: "Please go to 'Settings > Apps > Installed apps' to manually uninstall the programs listed below.",
  ko: "'설정 > 앱 > 설치된 앱'으로 이동하여 아래 목록의 프로그램을 직접 제거하세요.",
  ja: "「設定 > アプリ > インストールされているアプリ」に移動し、以下のリストにあるプログラムを手動でアンインストールしてください。",
  zh: "请前往\"设置 > 应用 > 安装的应用\"，手动卸载下方列出的程序。",
};

// 기타 메시지 다국어 지원
const translations = {
  en: {
    phaseA: "Phase A: Basic Removal",
    phaseB: "Phase B: Additional Removal Options",
    settingsAppRemove: "Open Settings > Apps...",
    forceRemove: "Force Remove",
    removeSuccess: "✅ Removed",
    removeFailed: "❌ Failed", 
    notRemoved: "⏭️ Not Removed",
    generateReport: "Generate Report",
    backToDashboard: "Back to Dashboard",
    allSuccessMessage: "✨ All programs successfully removed! You can now generate the report.",
    phaseACompleteMessage: "Phase A completed. Programs that failed need additional steps.",
    phaseBDescription: "The following programs couldn't be removed automatically. Choose your preferred removal method:",
    confirmForceRemove: "⚠️ Force removal can be risky. Are you sure you want to proceed?",
    checkRemovalStatus: "Check Status",
    proceedToReport: "Proceed to Report",
    scanAgain: "Scan Again",
    cleanSelected: "Clean Selected Items",
    tryScanAgain: "Try Scan Again",
    startPcScan: "Start PC Scan",
    verifyRemoval: "Verify Removal",
    clickSettingsInTaskbar: "⚠️ Click Settings in taskbar",
    verificationInfo: "💡 After removing programs through Windows Settings, click \"Verify Removal\" to update the status.",
    clickToCopyName: "Click program name to copy to clipboard",
    clickToRevealName: "Click and hold to reveal actual program name",
    copiedToClipboard: "Copied to clipboard!",
  },
  ko: {
    phaseA: "Phase A: 기본 제거",
    phaseB: "Phase B: 추가 제거 옵션",
    settingsAppRemove: "설정 열기 > 앱...",
    forceRemove: "강제 삭제",
    removeSuccess: "✅ 삭제 완료",
    removeFailed: "❌ 삭제 실패",
    notRemoved: "⏭️ 삭제 안 됨",
    generateReport: "리포트 작성",
    backToDashboard: "대시보드로 돌아가기",
    allSuccessMessage: "✨ 모든 프로그램이 성공적으로 제거되었습니다! 이제 리포트를 생성할 수 있습니다.",
    phaseACompleteMessage: "Phase A가 완료되었습니다. 실패한 프로그램은 추가 단계가 필요합니다.",
    phaseBDescription: "다음 프로그램들은 자동으로 제거되지 않았습니다. 원하는 제거 방법을 선택하세요:",
    confirmForceRemove: "⚠️ 강제 삭제는 위험할 수 있습니다. 정말로 진행하시겠습니까?",
    checkRemovalStatus: "상태 확인",
    proceedToReport: "리포트 진행",
    scanAgain: "다시 스캔",
    cleanSelected: "선택된 항목 정리",
    tryScanAgain: "다시 스캔 시도",
    startPcScan: "PC 스캔 시작",
    verifyRemoval: "제거 확인",
    clickSettingsInTaskbar: "⚠️ 작업 표시줄에서 설정 클릭",
    verificationInfo: "💡 Windows 설정을 통해 프로그램을 제거한 후, \"제거 확인\"을 클릭하여 상태를 업데이트하세요.",
    clickToCopyName: "프로그램 이름을 클릭하면 클립보드에 복사됩니다",
    clickToRevealName: "클릭하고 있으면 실제 프로그램 이름이 표시됩니다",
    copiedToClipboard: "클립보드에 복사되었습니다!",
  },
  ja: {
    phaseA: "Phase A: 基本削除",
    phaseB: "Phase B: 追加削除オプション",
    settingsAppRemove: "設定を開く > アプリ...",
    forceRemove: "強制削除",
    removeSuccess: "✅ 削除完了",
    removeFailed: "❌ 削除失敗",
    notRemoved: "⏭️ 削除されず",
    generateReport: "レポート作成",
    backToDashboard: "ダッシュボードに戻る",
    allSuccessMessage: "✨ すべてのプログラムが正常に削除されました！レポートを生成できます。",
    phaseACompleteMessage: "Phase Aが完了しました。失敗したプログラムは追加ステップが必要です。",
    phaseBDescription: "以下のプログラムは自動削除できませんでした。削除方法を選択してください：",
    confirmForceRemove: "⚠️ 強制削除は危険な場合があります。本当に続行しますか？",
    checkRemovalStatus: "状態確認",
    proceedToReport: "レポートへ進む",
    scanAgain: "再スキャン",
    cleanSelected: "選択されたアイテムをクリーンアップ",
    tryScanAgain: "スキャンを再試行",
    startPcScan: "PCスキャンを開始",
    verifyRemoval: "削除確認",
    clickSettingsInTaskbar: "⚠️ タスクバーで設定をクリック",
    verificationInfo: "💡 Windows設定でプログラムを削除した後、「削除確認」をクリックして状態を更新してください。",
    clickToCopyName: "プログラム名をクリックするとクリップボードにコピーされます",
    clickToRevealName: "クリックし続けると実際のプログラム名が表示されます",
    copiedToClipboard: "クリップボードにコピーしました！",
  },
  zh: {
    phaseA: "阶段A：基本删除",
    phaseB: "阶段B：额外删除选项",
    settingsAppRemove: "打开设置 > 应用...",
    forceRemove: "强制删除",
    removeSuccess: "✅ 删除成功",
    removeFailed: "❌ 删除失败",
    notRemoved: "⏭️ 未删除",
    generateReport: "生成报告",
    backToDashboard: "返回仪表板",
    allSuccessMessage: "✨ 所有程序成功删除！现在可以生成报告。",
    phaseACompleteMessage: "阶段A完成。需要额外步骤的程序。",
    phaseBDescription: "以下程序无法自动删除。请选择删除方式：",
    confirmForceRemove: "⚠️ 强制删除可能存在风险。确定要继续吗？",
    checkRemovalStatus: "检查状态",
    proceedToReport: "继续到报告",
    scanAgain: "重新扫描",
    cleanSelected: "清理选定项目",
    tryScanAgain: "重试扫描",
    startPcScan: "开始PC扫描",
    verifyRemoval: "验证删除",
    clickSettingsInTaskbar: "⚠️ 在任务栏中点击设置",
    verificationInfo: "💡 通过Windows设置删除程序后，点击\"验证删除\"更新状态。",
    clickToCopyName: "点击程序名称复制到剪贴板",
    clickToRevealName: "按住以显示实际程序名称",
    copiedToClipboard: "已复制到剪贴板！",
  }
};

// 수동 삭제 관련 다국어 지원
const manualCleanupTitles = {
  en: "Manual Cleanup Guide",
  ko: "수동 제거 가이드",
  ja: "手動削除ガイド",
  zh: "手动清理指南",
};

const uiOpenedMessages = {
  en: "✅ Windows Settings opened. Please manually remove:",
  ko: "✅ Windows 설정이 열렸습니다. 다음 프로그램을 직접 제거하세요:",
  ja: "✅ Windows設定が開きました。以下のプログラムを手動で削除してください:",
  zh: "✅ Windows设置已打开。请手动删除以下程序:",
};

const forceCleanButtonTexts = {
  en: "Attempt Force Removal",
  ko: "강제 삭제 시도",
  ja: "強制削除を試行",
  zh: "尝试强制删除",
};

const warningTexts = {
  en: "⚠️ This may be risky. Proceed with caution.",
  ko: "⚠️ 위험할 수 있습니다. 신중하게 결정하세요.",
  ja: "⚠️ 危険な可能性があります。慎重に判断してください。",
  zh: "⚠️ 这可能存在风险。请谨慎操作。",
};

const manualCleanupDescriptions = {
  en: {
    manualRequired: "The following programs require manual removal through Windows Settings:",
    forceOption: "For programs that couldn't be removed automatically, you can attempt force removal:"
  },
  ko: {
    manualRequired: "다음 프로그램은 Windows 설정을 통해 수동으로 제거해야 합니다:",
    forceOption: "자동으로 제거할 수 없는 프로그램에 대해 강제 제거를 시도할 수 있습니다:"
  },
  ja: {
    manualRequired: "以下のプログラムはWindows設定を通じて手動で削除する必要があります:",
    forceOption: "自動削除できないプログラムに対して強制削除を試行できます:"
  },
  zh: {
    manualRequired: "以下程序需要通过Windows设置手动删除:",
    forceOption: "对于无法自动删除的程序，您可以尝试强制删除:"
  }
};

export const SystemScanner = ({ setCurrentView, language }: SystemScannerProps) => {
  // 상태 관리
  const [step, setStep] = useState('idle'); // 'idle', 'scanning', 'results', 'cleaning', 'phase_b', 'report', 'error'
  const [scanResults, setScanResults] = useState<ScanResult[]>([]);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [finalReport, setFinalReport] = useState("");
  const [error, setError] = useState("");
  const [riskThreshold, setRiskThreshold] = useState(4); // 위험도 임계값 상태
  const [phaseAResults, setPhaseAResults] = useState<CleanupResult[]>([]);
  const [phaseStatus, setPhaseStatus] = useState<PhaseStatus>({});
  const [allResults, setAllResults] = useState<CleanupResult[]>([]);
  const [revealedPrograms, setRevealedPrograms] = useState<Set<string>>(new Set()); // 마스킹 해제된 프로그램들
  const [showLegalDisclaimer, setShowLegalDisclaimer] = useState(false); // 법적 고지 표시 여부
  const [copiedProgram, setCopiedProgram] = useState<string | null>(null); // 복사된 프로그램 이름
  
  const logContainerRef = useRef<HTMLDivElement>(null);
  const ws = useRef<WebSocket | null>(null);
  
  const t = translations[language as keyof typeof translations] || translations.en;

  // 백엔드 메시지 처리 핸들러
  const handleBackendMessage = (payload: string) => {
    try {
      const { type, data } = JSON.parse(payload) as BackendMessage;

      switch (type) {
        case 'scan_result':
          if (data && data.length > 0) {
            const initialResults = data.map((item: any) => ({ 
              ...item, 
              id: item.name, 
              masked_name: item.masked_name || item.name,
              clean: true 
            }));
            setScanResults(initialResults);
            setProgressLog(prev => [...prev, '📊 Scan complete. Review the results below.']);
            setStep('results');
          } else {
            // 위협이 발견되지 않았을 경우
            setFinalReport("🎉 Congratulations! No bloatware found in the system.");
            setStep('report');
          }
          break;

        case 'phase_a_complete':
          handlePhaseAComplete(data);
          break;

        case 'phase_b_complete':
          handlePhaseBComplete(data);
          break;

        case 'phase_c_complete':
          handlePhaseCComplete(data);
          break;

        case 'removal_verification':
          handleRemovalVerification(data);
          break;

        case 'final_report_generated':
          setFinalReport(data.llm_feedback);
          setStep('report');
          break;
  
        case 'progress':
          const status = typeof data === 'object' && data !== null && data.status ? data.status : data;
          setProgressLog(prev => [...prev, `[INFO] ${status}`]);
          break;

        case 'error':
          setError(data);
          setStep('error');
          break;
      }
    } catch (e) {
      // JSON 파싱 실패 시 일반 로그로 처리
      setProgressLog(prev => [...prev, `[LOG] ${payload}`]);
    }
  };

  // Phase A 완료 처리
  const handlePhaseAComplete = (data: any) => {
    const results = data.results || [];
    setPhaseAResults(results);
    setAllResults(results);
    
    // Phase 상태 초기화
    const newStatus: PhaseStatus = {};
    results.forEach((result: CleanupResult) => {
      newStatus[result.name] = {
        phase_a: result.status === 'success' ? 'success' : 'failed'
      };
    });
    setPhaseStatus(newStatus);

    // 실패한 항목이 있는지 확인
    const failedItems = results.filter((r: CleanupResult) => r.status !== 'success');

    if (failedItems.length === 0) {
      // 모두 성공 - 바로 최종 리포트 생성
      setProgressLog(prev => [...prev, t.allSuccessMessage]);
      ws.current?.send(JSON.stringify({
        command: "generate_comprehensive_report",
        args: [JSON.stringify(results), language]
      }));
    } else {
      // 실패 항목이 있음 - Phase B로
      setProgressLog(prev => [...prev, t.phaseACompleteMessage]);
      setStep('phase_b');
    }
  };

  // Phase B 완료 처리 (자동화 관련 로직 제거)
  const handlePhaseBComplete = (data: any) => {
    const results = data.results || [];
    
    results.forEach((result: CleanupResult) => {
      setPhaseStatus(prev => ({
        ...prev,
        [result.name]: {
          ...prev[result.name],
          phase_b: 'in_progress'
        }
      }));
      
      setProgressLog(prev => [...prev, `✅ Windows Settings opened for ${result.masked_name}. Please search and remove manually.`]);
    });
  };

  // Phase C 완료 처리
  const handlePhaseCComplete = (data: any) => {
    const results = data.results || [];
    
    results.forEach((result: CleanupResult) => {
      setPhaseStatus(prev => ({
        ...prev,
        [result.name]: {
          ...prev[result.name],
          phase_c: result.status === 'success' ? 'success' : 'failed'
        }
      }));
      
      // 전체 결과에 추가
      setAllResults(prev => {
        const existingIndex = prev.findIndex(r => r.name === result.name);
        if (existingIndex >= 0) {
          const updated = [...prev];
          updated[existingIndex] = { ...updated[existingIndex], ...result };
          return updated;
        }
        return [...prev, result];
      });
    });
  };

  // 개별 프로그램 제거 확인 처리
  const handleRemovalVerification = (data: any) => {
    const { program_name, is_removed } = data;
    
    setPhaseStatus(prev => ({
      ...prev,
      [program_name]: {
        ...prev[program_name],
        phase_b: is_removed ? 'completed' : 'in_progress',
        removal_verified: is_removed
      }
    }));
    
    if (is_removed) {
      setProgressLog(prev => [...prev, `✅ ${program_name} has been successfully removed!`]);
    } else {
      setProgressLog(prev => [...prev, `❌ ${program_name} is still installed.`]);
    }
  };

  // 모든 프로그램의 제거 상태 확인
  const checkRemovalStatus = async () => {
    setProgressLog(prev => [...prev, "🔍 Checking removal status..."]);
    
    const programsToCheck = phaseAResults
      .filter(r => r.status !== 'success')
      .map(r => r.name);
    
    ws.current?.send(JSON.stringify({
      command: "check_removal_status",
      args: [JSON.stringify(programsToCheck)]
    }));
  };

  // WebSocket 연결 설정
  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8765');
    ws.current.onopen = () => {
      setProgressLog(["[INFO] Ready to scan."]);
    };
    ws.current.onmessage = (event) => {
      handleBackendMessage(event.data);
    };
    ws.current.onerror = () => {
      setError("Connection to server failed. Please ensure the server is running.");
      setStep('error');
    };
    return () => {
      ws.current?.close();
    };
  }, []);

  // 로그 자동 스크롤
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [progressLog]);

  // 스캔 시작
  const handleScan = () => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setError("Server is not connected.");
      setStep('error');
      return;
    }
    
    // 상태 초기화
    setStep('scanning');
    setScanResults([]);
    setPhaseAResults([]);
    setPhaseStatus({});
    setAllResults([]);
    setProgressLog(['🔍 Starting system scan...']);
    setError("");
    setFinalReport("");

    // scan 요청 시 riskThreshold도 함께 전달
    ws.current.send(JSON.stringify({ 
      command: "scan",
      args: ["[]", riskThreshold.toString()]
    }));
  };
  
  // Phase A 시작 (기본 정리)
  const handleClean = () => {
    // 법적 고지를 먼저 표시
    if (!showLegalDisclaimer) {
      const userAccepted = window.confirm(legalDisclaimer[language as keyof typeof legalDisclaimer] || legalDisclaimer['en']);
      if (!userAccepted) return;
      setShowLegalDisclaimer(true);
    }
    
    // 일반 경고
    const userConfirmed = window.confirm(warnings[language as keyof typeof warnings] || warnings['en']);
    if (!userConfirmed) return;

    if (ws.current?.readyState !== WebSocket.OPEN) {
      setError("Server is not connected.");
      setStep('error');
      return;
    }
    
    const itemsToClean = scanResults.filter(item => item.clean);
    if (itemsToClean.length === 0) {
      alert("Please select at least one item to clean.");
      return;
    }
    
    setStep('cleaning');
    setProgressLog(prev => [...prev, `🧹 ${t.phaseA}: Starting cleanup of ${itemsToClean.length} items...`]);

    ws.current.send(JSON.stringify({ 
      command: "phase_a_clean", 
      args: [JSON.stringify(itemsToClean), language] 
    }));
  };

  // Phase B - UI 기반 삭제
  const handlePhaseB = (programName: string) => {
    setProgressLog(prev => [...prev, `📱 Opening Windows Settings for ${programName}...`]);
    
    // 상태를 'in_progress'로 변경
    setPhaseStatus(prev => ({
      ...prev,
      [programName]: {
        ...prev[programName],
        phase_b: 'in_progress'
      }
    }));
    
    ws.current?.send(JSON.stringify({
      command: "phase_b_clean",
      args: [JSON.stringify([{ name: programName }]), language]
    }));
  };

  // Phase C - 강제 삭제
  const handlePhaseC = (programName: string) => {
    const confirmed = window.confirm(t.confirmForceRemove);
    if (!confirmed) return;

    setProgressLog(prev => [...prev, `💪 Attempting force removal of ${programName}...`]);
    
    ws.current?.send(JSON.stringify({
      command: "phase_c_clean",
      args: [JSON.stringify([{ name: programName }]), language]
    }));
  };

  // 개별 프로그램 제거 확인
  const verifyRemoval = (programName: string) => {
    setProgressLog(prev => [...prev, `Verifying removal of ${programName}...`]);
    
    ws.current?.send(JSON.stringify({
      command: "verify_removal",
      args: [programName]
    }));
  };
  
  // 모든 항목이 처리되었는지 확인
  const allItemsProcessed = () => {
    return phaseAResults
      .filter(r => r.status !== 'success')
      .every(item => {
        const status = phaseStatus[item.name];
        return status?.phase_b === 'completed' || 
               status?.phase_c === 'success' ||
               status?.removal_verified ||
               status?.phase_b === 'skipped';
      });
  };

  // 종합 리포트 생성
  const handleGenerateReport = () => {
    setProgressLog(prev => [...prev, "📋 Generating comprehensive report..."]);
    
    // 최종 결과 수집
    const finalResults = [...allResults];
    
    // Phase B에서 처리되지 않은 항목들 처리
    phaseAResults.forEach(result => {
      if (result.status !== 'success') {
        const status = phaseStatus[result.name];
        
        // 이미 allResults에 있는지 확인
        const existingIndex = finalResults.findIndex(r => r.name === result.name);
        
        if (status?.phase_b === 'skipped' || (!status?.phase_b && !status?.phase_c)) {
          // 사용자가 아무 작업도 하지 않은 경우
          const skipResult = {
            ...result,
            status: 'manual_required' as const,
            message: 'User chose not to remove',
            phase_completed: 'skipped'
          };
          
          if (existingIndex >= 0) {
            finalResults[existingIndex] = skipResult;
          } else {
            finalResults.push(skipResult);
          }
        } else if (status?.removal_verified) {
          // 수동으로 제거 확인된 경우
          const verifiedResult = {
            ...result,
            status: 'success' as const,
            message: 'Manually removed through Windows Settings',
            phase_completed: 'phase_b'
          };
          
          if (existingIndex >= 0) {
            finalResults[existingIndex] = verifiedResult;
          } else {
            finalResults.push(verifiedResult);
          }
        }
      }
    });
    
    ws.current?.send(JSON.stringify({
      command: "generate_comprehensive_report",
      args: [JSON.stringify(finalResults), language]
    }));
  };

  const handleBackToDashboard = () => {
    // 스캔 결과가 있고, 아직 정리(cleaning)나 리포트 단계가 아닐 때 경고
    if (scanResults.length > 0 && (step === 'results' || step === 'cleaning')) {
      if (window.confirm("Warning: If you go back, the current scan results will be discarded. Are you sure?")) {
        setCurrentView('dashboard');
      }
    } else {
      setCurrentView('dashboard');
    }
  };
  
  // 프로그램 이름 클릭 핸들러 (Phase B용 - 클립보드 복사)
  const handleProgramNameClick = async (programName: string) => {
    try {
      await navigator.clipboard.writeText(programName);
      setCopiedProgram(programName);
      setTimeout(() => setCopiedProgram(null), 2000); // 2초 후 메시지 제거
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  // 프로그램 이름 마우스 다운/업 핸들러 (Phase A용 - 마스킹 해제)
  const handleProgramMouseDown = (programName: string) => {
    setRevealedPrograms(prev => new Set(prev).add(programName));
  };

  const handleProgramMouseUp = (programName: string) => {
    setRevealedPrograms(prev => {
      const newSet = new Set(prev);
      newSet.delete(programName);
      return newSet;
    });
  };

  const handleProgramMouseLeave = (programName: string) => {
    setRevealedPrograms(prev => {
      const newSet = new Set(prev);
      newSet.delete(programName);
      return newSet;
    });
  };

  const toggleClean = (id: string) => {
    setScanResults(scanResults.map(item => 
      item.id === id ? { ...item, clean: !item.clean } : item
    ));
  };

  // 강제 삭제 확인 함수
  const handleForceCleanConfirmation = (failedItems: CleanupResult[]) => {
    const forceCleanableItems = failedItems.filter(item =>
      item.status === 'manual_required' || item.force_failed
    );
    
    if (forceCleanableItems.length === 0) {
      return;
    }
    
    const confirmMessages = {
      en: `⚠️ Automatic removal failed for:\n${forceCleanableItems.map(item => `• ${item.guide_masked_name || item.masked_name}`).join('\n')}\n\nAttempt forceful removal? (This may be risky)`,
      ko: `⚠️ 자동 제거 실패:\n${forceCleanableItems.map(item => `• ${item.guide_masked_name || item.masked_name}`).join('\n')}\n\n강제 제거를 시도할까요? (위험할 수 있음)`,
      ja: `⚠️ 自動削除に失敗しました:\n${forceCleanableItems.map(item => `• ${item.guide_masked_name || item.masked_name}`).join('\n')}\n\n強制的な削除を試行しますか？ (危険な可能性があります)`,
      zh: `⚠️ 自动清理失败:\n${forceCleanableItems.map(item => `• ${item.guide_masked_name || item.masked_name}`).join('\n')}\n\n尝试强制删除？ (可能存在风险)`,
    };

    const confirmMessage = confirmMessages[language as keyof typeof confirmMessages] || confirmMessages.en;
    const userConfirmed = window.confirm(confirmMessage);
    
    if (userConfirmed && ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        command: "force_clean",
        args: [JSON.stringify(forceCleanableItems), language]
      }));
    }
  };

  // 렌더링 함수들
  const renderIdle = () => (
    <>
      <div className="risk-info">
        <h4>Risk Score Guide</h4>
        <p><span className="risk-high">7-10:</span> Harmful, recommend immediate deletion.</p>
        <p><span className="risk-medium">4-6:</span> Bloatware, consumes resources.</p>
        <p><span className="risk-low">1-3:</span> Normal program. (Not typically shown)</p>
        <p><span className="risk-safe">0:</span> Essential system component.</p>
      </div>
      <div className="risk-slider-container">
        <label htmlFor="risk-slider">Minimum Risk Score to Scan: {riskThreshold}</label>
        <input 
          type="range"
          id="risk-slider"
          min="0"
          max="10"
          value={riskThreshold}
          onChange={(e) => setRiskThreshold(Number(e.target.value))}
          className="risk-slider"
        />
      </div>
      <button onClick={handleScan} className="start-button">
        {t.startPcScan}
      </button>
      <button type="button" onClick={handleBackToDashboard}>
        {t.backToDashboard}
      </button>
    </>
  );

  const renderProgress = () => (
    <div className="report-box progress-log" ref={logContainerRef}>
      <h4>Progress</h4>
      {progressLog.map((log, i) => <p key={i}>{log}</p>)}
    </div>
  );

  const renderResults = () => (
    <div className="results-container">
      <h4>Scan Results</h4>
      <p className="info-text">{t.clickToRevealName}</p>
      <div className="results-list">
        {scanResults.map(item => (
          <div key={item.id} className="result-item">
            <input 
              type="checkbox" 
              id={`clean-${item.id}`} 
              checked={!!item.clean} 
              onChange={() => toggleClean(item.id)} 
            />
            <label htmlFor={`clean-${item.id}`}>
              <strong 
                className="program-name-interactive"
                onMouseDown={() => handleProgramMouseDown(item.name)}
                onMouseUp={() => handleProgramMouseUp(item.name)}
                onMouseLeave={() => handleProgramMouseLeave(item.name)}
                onTouchStart={() => handleProgramMouseDown(item.name)}
                onTouchEnd={() => handleProgramMouseUp(item.name)}
              >
                {revealedPrograms.has(item.name) ? item.name : item.masked_name}
              </strong> (Risk: {item.risk_score})
              <span className="reason">{item.reason}</span>
            </label>
          </div>
        ))}
      </div>
      <div className="row">
        <button onClick={handleClean} disabled={scanResults.filter(i => i.clean).length === 0}>
          {t.cleanSelected}
        </button>
        <button type="button" onClick={handleScan}>
          {t.scanAgain}
        </button>
        <button type="button" onClick={handleBackToDashboard}>
          {t.backToDashboard}
        </button>
      </div>
    </div>
  );

  // Phase B 렌더링
  const renderPhaseB = () => {
    const failedItems = phaseAResults.filter(r => r.status !== 'success');
    
    return (
      <div className="phase-b-container">
        <h3>{t.phaseB}</h3>
        <p className="phase-description">{t.phaseBDescription}</p>
        <p className="info-text">{t.clickToCopyName}</p>
        
        <div className="phase-b-items">
          {failedItems.map(item => {
            const status = phaseStatus[item.name] || {};
            const isInProgress = status.phase_b === 'in_progress';
            const isCompleted = status.phase_b === 'completed';
            
            return (
              <div key={item.name} className="phase-b-item">
                <span 
                  className="program-name clickable"
                  onClick={() => handleProgramNameClick(item.name)}
                  title="Click to copy program name"
                >
                  {item.masked_name}
                  {copiedProgram === item.name && (
                    <span className="copied-message">{t.copiedToClipboard}</span>
                  )}
                </span>
                
                <div className="action-buttons">
                  {/* Phase B 상태 표시 */}
                  {isCompleted ? (
                    <span className="status-success">{t.removeSuccess}</span>
                  ) : isInProgress ? (
                    <button 
                      className="verify-btn"
                      onClick={() => verifyRemoval(item.name)}
                    >
                      {t.verifyRemoval}
                    </button>
                  ) : (
                    <button 
                      className="phase-b-btn"
                      onClick={() => handlePhaseB(item.name)}
                      disabled={status.phase_c === 'success'}
                    >
                      {t.settingsAppRemove}
                    </button>
                  )}
                  
                  {/* Phase C 버튼 - Phase B가 완료되지 않았거나 실패한 경우에만 표시 */}
                  {!isCompleted && (
                    status.phase_c === 'success' ? (
                      <span className="status-success">{t.removeSuccess}</span>
                    ) : status.phase_c === 'failed' ? (
                      <span className="status-failed">{t.removeFailed}</span>
                    ) : (
                      <button 
                        className="phase-c-btn"
                        onClick={() => handlePhaseC(item.name)}
                        disabled={isInProgress}
                      >
                        {t.forceRemove}
                      </button>
                    )
                  )}
                </div>
              </div>
            );
          })}
        </div>
        
        <div className="phase-b-info">
          <p className="info-text">
            {t.verificationInfo}
          </p>
        </div>
        
        <div className="phase-actions">
          <button onClick={checkRemovalStatus} className="check-btn">
            {t.checkRemovalStatus} (All)
          </button>
          <button 
            onClick={handleGenerateReport} 
            className="report-btn"
            disabled={!allItemsProcessed()}
          >
            {t.proceedToReport}
          </button>
          <button onClick={() => setCurrentView('dashboard')} className="back-btn">
            {t.backToDashboard}
          </button>
        </div>
      </div>
    );
  };

  // 리포트 렌더링
  const renderReport = () => {
    // allResults에서 수동 제거가 필요한 항목들 찾기
    const manualItems = allResults.filter(item => 
      item.status === 'manual_required' || item.status === 'ui_opened'
    );
    const forceFailedItems = allResults.filter(item => 
      item.status === 'manual_required' && item.force_failed
    );
  
    return (
      <div className="report-box">
        <h3>Final Report</h3>
        <pre>{finalReport}</pre>
  
        {/* 수동 제거 가이드 */}
        {manualItems.length > 0 && (
          <div className="manual-cleanup-guide">
            <h4>{manualCleanupTitles[language as keyof typeof manualCleanupTitles] || manualCleanupTitles['en']}</h4>
            
            {/* UI가 열린 항목들 */}
            {manualItems.filter(item => item.ui_opened).length > 0 && (
              <div className="ui-opened-section">
                <p className="success-msg">
                  {uiOpenedMessages[language as keyof typeof uiOpenedMessages] || uiOpenedMessages.en}
                </p>
                <ul>
                  {manualItems.filter(item => item.ui_opened).map(item => (
                    <li key={item.name} className="ui-opened-item">
                      <span>{item.guide_masked_name || item.masked_name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {/* 일반적인 수동 제거가 필요한 항목들 */}
            {manualItems.filter(item => !item.ui_opened).length > 0 && (
              <div className="manual-removal-section">
                <p>{manualCleanupDescriptions[language as keyof typeof manualCleanupDescriptions]?.manualRequired || manualCleanupDescriptions.en.manualRequired}</p>
                <p className="guide-text">{guideTexts[language as keyof typeof guideTexts] || guideTexts['en']}</p>
                <ul>
                  {manualItems.filter(item => !item.ui_opened).map(item => (
                    <li key={item.name}>
                      <span>{item.guide_masked_name || item.masked_name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {/* 강제 삭제 옵션 (실패한 항목들에 대해) */}
            {forceFailedItems.length > 0 && (
              <div className="force-clean-option">
                <p className="force-option-desc">
                  {manualCleanupDescriptions[language as keyof typeof manualCleanupDescriptions]?.forceOption || manualCleanupDescriptions.en.forceOption}
                </p>
                <button 
                  className="force-clean-btn"
                  onClick={() => handleForceCleanConfirmation(forceFailedItems)}
                >
                  {forceCleanButtonTexts[language as keyof typeof forceCleanButtonTexts] || forceCleanButtonTexts['en']}
                </button>
                <small className="warning-text">
                  {warningTexts[language as keyof typeof warningTexts] || warningTexts.en}
                </small>
              </div>
            )}
          </div>
        )}
  
        <button type="button" onClick={handleScan}>
          {t.scanAgain}
        </button>
        <button type="button" onClick={handleBackToDashboard}>
          {t.backToDashboard}
        </button>
      </div>
    );
  };

  const renderError = () => (
    <div className="error-container">
      <h3>Error</h3>
      <pre className="error-log">{error}</pre>
      <button type="button" onClick={handleScan}>
        {t.tryScanAgain}
      </button>
      <button type="button" onClick={handleBackToDashboard}>
        {t.backToDashboard}
      </button>
    </div>
  );

  return (
    <div className="container system-scanner">
      <h2>💻 Scan & Clean PC</h2>
      {step === 'idle' && renderIdle()}
      {(step === 'scanning' || step === 'cleaning') && renderProgress()}
      {step === 'results' && renderResults()}
      {step === 'phase_b' && renderPhaseB()}
      {step === 'report' && renderReport()}
      {step === 'error' && renderError()}
    </div>
  );
};