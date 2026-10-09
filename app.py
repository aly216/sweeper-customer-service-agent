import time
import streamlit as st
from agent.react_agent import ReactAgent
from utils import storage

storage.init_db()

# 标题
st.title("智扫通机器人智能客服")
st.divider()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = ""

with st.sidebar:
    st.subheader("账户")
    if st.session_state["logged_in"]:
        user = storage.get_user(st.session_state["user_id"])
        profile = (user or {}).get("profile", "")
        st.write(f"当前用户：{st.session_state['user_id']} · {profile}")
        if st.button("退出登录"):
            st.session_state["logged_in"] = False
            st.session_state["user_id"] = ""
            st.rerun()
    else:
        mode = st.radio("模式", ["登录", "注册"], horizontal=True)
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        if mode == "注册":
            profile = st.text_input("画像（如：65㎡公寓 | 单身 | 木地板）")
            if st.button("注册并登录"):
                if not username or not password:
                    st.warning("用户名和密码不能为空")
                else:
                    try:
                        uid = storage.create_user(username, password, profile)
                        st.session_state["logged_in"] = True
                        st.session_state["user_id"] = uid
                        st.success("注册成功")
                        st.rerun()
                    except ValueError as e:
                        st.warning(str(e))
        else:
            if st.button("登录"):
                uid = storage.verify_user(username, password)
                if uid is None:
                    st.warning("用户名或密码错误")
                else:
                    st.session_state["logged_in"] = True
                    st.session_state["user_id"] = uid
                    st.rerun()

if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

if 'messages' not in st.session_state:
    st.session_state['messages'] = []

for message in st.session_state['messages']:
    st.chat_message(message['role']).write(message['content'])


prompt=st.chat_input()
if prompt:
    st.chat_message("user").write(prompt)
    st.session_state['messages'].append({'role': 'user', 'content': prompt})
    
    cache_list = []
    with st.spinner("思考中..."):
        # 多轮记忆：把完整对话历史传给 agent（模型无状态，每轮需重新喂历史）
        history = [{'role': m['role'], 'content': m['content']} for m in st.session_state['messages']]
        res_stream = st.session_state['agent'].execute_stream(
            history, user_id=st.session_state.get("user_id", ""))


        def capture(generator,cache_list):
            for chunk in generator:
                cache_list.append(chunk)
                yield chunk
                
        st.chat_message("assistant").write_stream(capture(res_stream,cache_list))
        st.session_state['messages'].append({'role': 'assistant', 'content': "".join(cache_list)})
        st.rerun()
