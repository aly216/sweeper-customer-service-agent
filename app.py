import time
import streamlit as st
from agent.react_agent import ReactAgent



# 标题
st.title("智扫通机器人智能客服")
st.divider()

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
        res_stream = st.session_state['agent'].execute_stream(prompt)


        def capture(generator,cache_list):
            for chunk in generator:
                cache_list.append(chunk)
                yield chunk
                
        st.chat_message("assistant").write_stream(capture(res_stream,cache_list))
        st.session_state['messages'].append({'role': 'assistant', 'content': "".join(cache_list)})
        st.rerun()
