import { navigate } from '../main.js';

// const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const API_URL =  'http://127.0.0.1:8000';


export function renderLogin(){
    return `
    <form id="login-container">
        <input type="email" required placeholder="Email" id="loginEmail">
        <input type="password" required placeholder="Password" id="loginPass">
        <button type="submit" id="loginBtn">Login</button>
    </form>
    `;
}

export function initLogin() {
    const loginContainer = document.getElementById("login-container")
    const email = document.getElementById('loginEmail');
    const password = document.getElementById('loginPass');
    const loginBtn = document.getElementById('loginBtn')

    loginBtn.addEventListener('click', async (e) => {
        e.preventDefault()
        if(!loginContainer.checkValidity()){
            alert("Enter Credentials")
            return
        }
        try{
            const res = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: {
                "Content-Type" : "application/x-www-form-urlencoded"
            },
            body: new URLSearchParams({ username: email.value, password : password.value })
            });
            const data = await res.json();
            if (!res.ok){
                throw{
                    message: data.detail
                }
            }
            alert("LOGIN SUCCESSFUL")
        }catch(message){
            alert(message.message)
        }
    });
}
