import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt
from google import genai

load_dotenv()

api_key_1 = os.getenv("GEMINI_API_KEY")
api_key_2 = os.getenv("GEMINI_API_KEY_2")

CHAVES_API = [k for k in [api_key_1, api_key_2] if k]

if not CHAVES_API:
    raise RuntimeError("Nenhuma GEMINI_API_KEY configurada no ficheiro .env")

SECRET_KEY = "chave_secreta_super_segura_para_empresa_mudar_em_producao"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(title="IA Corporativa Segura")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

SENHA_DELL_HASH = hash_password("Dell@2020")

USUARIOS_DB = {
    "seculos": {
        "username": "Seculos",
        "hashed_password": SENHA_DELL_HASH,
        "role": "admin",
        "nome": "Seculos"
    },
    "matheus": {
        "username": "Matheus",
        "hashed_password": SENHA_DELL_HASH,
        "role": "admin",
        "nome": "Matheus"
    }
}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou sessão expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username.lower() not in USUARIOS_DB:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return USUARIOS_DB[username.lower()]

class Pergunta(BaseModel):
    pergunta: str

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_key = form_data.username.lower()
    user = USUARIOS_DB.get(user_key)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário ou senha incorretos"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "nome": user["nome"],
        "role": user["role"]
    }

@app.post("/chat")
def chat(dados: Pergunta, current_user: dict = Depends(get_current_user)):
    user_role = current_user["role"]
    
    # Injeta a data e hora do servidor em tempo real (Horário de Brasília)
    agora = datetime.now()
    data_hora_formatada = agora.strftime("%d/%m/%Y às %H:%M:%S")

    instrucao_permissao = (
        f"Você é o Assistente Corporativo da Empresa. "
        f"Usuário autenticado: {current_user['nome']} (Acesso: {user_role.upper()}). "
        f"Data e hora atual (Horário Local/Brasília): {data_hora_formatada}."
    )

    ultimo_erro = ""
    for chave in CHAVES_API:
        try:
            client = genai.Client(api_key=chave)
            resposta = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=f"{instrucao_permissao}\nPergunta: {dados.pergunta}"
            )
            return {"resposta": resposta.text, "usuario": current_user["nome"], "permissao": user_role}
        except Exception as e:
            ultimo_erro = str(e)
            continue

    if "429" in ultimo_erro or "RESOURCE_EXHAUSTED" in ultimo_erro:
        return {"resposta": "Atingiu o limite temporário de requisições por minuto do plano gratuito. Aguarde cerca de 30 segundos e tente novamente."}
    if "503" in ultimo_erro or "UNAVAILABLE" in ultimo_erro:
        return {"resposta": "O serviço do Gemini está temporariamente sobrecarregado. Aguarde alguns segundos e tente novamente."}

    return {"resposta": f"Não foi possível obter resposta do servidor. Detalhes: {ultimo_erro}"}