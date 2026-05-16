#!/bin/bash
# WSL2起動時に AyumiDB デーモンを自動起動する設定
# これを実行すると ~/.bashrc に起動スクリプトが追記される

SCRIPT="~/ayumindb/scripts/start_daemons.sh"
LINE="bash $SCRIPT"

if grep -q "start_daemons.sh" ~/.bashrc 2>/dev/null; then
    echo "✅ 既に設定済み: ~/.bashrc に start_daemons.sh が登録されています"
else
    cat >> ~/.bashrc << EOF

# AyumiDB デーモン自動起動
if [[ -z "\$TMUX" ]] && [[ "\$(tty)" =~ /dev/tty ]]; then
    bash $SCRIPT
fi
EOF
    echo "✅ ~/.bashrc に自動起動設定を追跡しました"
    echo "   次回 WSL2 起動時にバックフィルとモニターが自動開始します"
    echo "   手動で開始する場合: bash $SCRIPT"
fi
