"""
Script para limpar o banco de dados.

Remove todos os registros da tabela 'processed'.
"""

import os
import psycopg2
import time
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def limpar_banco():
    """Limpa todos os registros do banco de dados."""
    if not DATABASE_URL:
        print("❌ Erro: DATABASE_URL não configurada no .env")
        return False
    
    max_tentativas = 5
    tentativa = 0
    
    while tentativa < max_tentativas:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            
            # Conta registros antes
            cur.execute("SELECT COUNT(*) FROM processed")
            total_antes = cur.fetchone()[0]
            
            # Limpa a tabela
            cur.execute("DELETE FROM processed")
            conn.commit()
            
            # Conta depois
            cur.execute("SELECT COUNT(*) FROM processed")
            total_depois = cur.fetchone()[0]
            
            cur.close()
            conn.close()
            
            print("=" * 60)
            print("✅ BANCO LIMPO COM SUCESSO!")
            print("=" * 60)
            print(f"  Registros antes: {total_antes}")
            print(f"  Registros depois: {total_depois}")
            print("=" * 60)
            return True
                
        except psycopg2.OperationalError as e:
            if "database is locked" in str(e):
                tentativa += 1
                if tentativa < max_tentativas:
                    print(f"⏳ Banco bloqueado, tentando novamente em 2 segundos... (tentativa {tentativa}/{max_tentativas})")
                    time.sleep(2)
                else:
                    print("=" * 60)
                    print("❌ ERRO: Banco de dados está bloqueado")
                    print("=" * 60)
                    print("  O banco está sendo usado por outro processo.")
                    print("  Faça o seguinte:")
                    print("  1. Pare o scheduler (Ctrl+C se estiver rodando)")
                    print("  2. Aguarde alguns segundos")
                    print("  3. Execute novamente: python3 clear_db.py")
                    print()
                    print("=" * 60)
                    return False
            else:
                print(f"❌ Erro ao limpar banco: {e}")
                return False
        except psycopg2.Error as e:
            print(f"❌ Erro ao acessar banco PostgreSQL: {e}")
            return False
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
            return False
    
    return False


if __name__ == "__main__":
    limpar_banco()

