#!/bin/bash
#===============================================================================
#  validate_fase0.sh – Validação Fase Zero Roaz Codex
#  Executar como root (sudo)
#===============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }

header() { echo -e "\n${YELLOW}=== $1 ===${NC}"; }

# =============================================================================
# Configuração do Ambiente Oracle (MUITO IMPORTANTE)
# =============================================================================
header "Configurando Ambiente Oracle 23.26"

ORACLE_HOME="/llm_nvme/u01/app/oracle/product/23.26.1/dbhome_1"
export ORACLE_HOME
export PATH=$ORACLE_HOME/bin:$PATH
export LD_LIBRARY_PATH=$ORACLE_HOME/lib:/lib:/usr/lib

# Carregar perfil do oracle como fallback
if [[ -f /home/oracle/.bash_profile ]]; then
    source /home/oracle/.bash_profile 2>/dev/null && \
    pass "Perfil .bash_profile do oracle carregado" || \
    warn "Falha ao carregar .bash_profile"
fi

# Verifica se sqlplus está disponível
if command -v sqlplus >/dev/null 2>&1; then
    pass "sqlplus encontrado em $ORACLE_HOME"
else
    fail "sqlplus não encontrado após configuração do ORACLE_HOME"
fi

echo "ORACLE_HOME configurado: $ORACLE_HOME"

#===============================================================================
# 1. Sistema Operacional e Kernel
#===============================================================================
header "Sistema e Kernel"
grep -q "Oracle Linux" /etc/os-release && pass "Oracle Linux detectado" || fail "Oracle Linux não detectado"
uname -m | grep -q x86_64 && pass "Arquitetura x86_64" || fail "Arquitetura inválida"

CPU_COUNT=$(nproc)
[[ $CPU_COUNT -ge 8 ]] && pass "CPUs: ${CPU_COUNT} (>=8)" || fail "CPUs: ${CPU_COUNT} (mínimo 8 recomendado)"

#===============================================================================
# 2. Memória e Armazenamento
#===============================================================================
header "Memória e Armazenamento"
memtotal=$(grep MemTotal /proc/meminfo | awk '{print $2}')
[[ "$memtotal" -ge 88000000 ]] && \
    pass "RAM: $((memtotal/1024/1024)) GB (>=84 GB)" || \
    fail "RAM insuficiente: $((memtotal/1024/1024)) GB"

mountpoint -q /llm_nvme && pass "/llm_nvme montado" || fail "/llm_nvme não está montado"

avail=$(df -BG /llm_nvme | tail -1 | awk '{print $4}' | tr -d 'G')
[[ "$avail" -ge 500 ]] && pass "Espaço livre /llm_nvme: ${avail} GB" || \
warn "Espaço livre /llm_nvme: ${avail} GB (recomendado >= 500 GB)"

#===============================================================================
# 3. Diretórios do Projeto
#===============================================================================
header "Diretórios do Roaz"
BASE="/llm_nvme/roaz"
[ -d "$BASE" ] && pass "Diretório base $BASE" || fail "Diretório base não encontrado"

for d in src/harvester src/processor src/vectorizer src/rag src/utils src/router \
         configs scripts sql data/staging data/raw data/csv tests docs; do
    [ -d "$BASE/$d" ] && pass "  $d" || fail "  $d"
done

[ -d "/llm_nvme/parquet/roaz" ] && pass "Diretório Parquet existe" || fail "Diretório Parquet ausente"

#===============================================================================
# 4. Arquivos de Configuração
#===============================================================================
header "Arquivos de Configuração"
[ -f "$BASE/.env" ] && pass ".env encontrado" || fail ".env ausente"
[ -f "$BASE/configs/sources.yaml" ] && pass "sources.yaml encontrado" || fail "sources.yaml ausente"
[ -f "$BASE/data/csv/oracle_db_26_docs.csv" ] && pass "CSV de documentos encontrado" || fail "CSV ausente"

#===============================================================================
# 5. Ambiente Python
#===============================================================================
header "Ambiente Python"
VENV="$BASE/.venv/bin/activate"
[ -f "$VENV" ] && {
    source "$VENV" 2>/dev/null
    pass "Virtual Environment ativado"
} || fail "Virtual Environment não encontrado"

python --version 2>&1 | grep -q "3.12" && pass "Python 3.12" || warn "Versão Python diferente de 3.12"

for pkg in torch sentence-transformers transformers accelerate bitsandbytes oracledb pandas pyarrow; do
    pip show "$pkg" &>/dev/null && pass "  $pkg" || fail "  $pkg"
done

python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null && \
    pass "CUDA disponível no PyTorch" || fail "CUDA não disponível"

#===============================================================================
# 6. Ferramentas
#===============================================================================
header "Ferramentas do Sistema"
for cmd in git gcc make sqlplus; do
    command -v $cmd &>/dev/null && pass "$cmd OK" || fail "$cmd não encontrado"
done

#===============================================================================
# 7. Banco de Dados Oracle
#===============================================================================
header "Oracle Database (roaz)"
if echo "exit" | sqlplus -S roaz/oracle@appspdb &>/dev/null; then
    pass "Conexão com usuário roaz OK"
else
    fail "Falha na conexão com o banco (verifique senha ou listener)"
fi

#===============================================================================
# 8. Permissões
#===============================================================================
header "Permissões de Escrita"
touch "$BASE/.write_test" 2>/dev/null && rm -f "$BASE/.write_test" && pass "Escrita em $BASE OK" || fail "Sem permissão em $BASE"
touch "/llm_nvme/parquet/roaz/.write_test" 2>/dev/null && rm -f "/llm_nvme/parquet/roaz/.write_test" && pass "Escrita em Parquet OK" || fail "Sem permissão no Parquet"

#===============================================================================
# 9. Resumo
#===============================================================================
header "RESUMO FINAL"
echo -e "✅ Sucessos : ${GREEN}$PASS${NC}"
echo -e "❌ Falhas   : ${RED}$FAIL${NC}"

if [ $FAIL -eq 0 ]; then
    echo -e "\n${GREEN}Fase Zero validada com sucesso!${NC}"
else
    echo -e "\n${RED}Existem $FAIL problema(s) a corrigir.${NC}"
fi
