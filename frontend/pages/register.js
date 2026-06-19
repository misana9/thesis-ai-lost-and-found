import { navigate } from '../main.js';

// const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const API_URL =  'http://127.0.0.1:8000';

export function renderRegister(){
    return `
    <form id="register-container">
        <input type="String" required placeholder="Full Name" id="registerName">
        <input type="email" required placeholder="Email" id="registerEmail">
        <input type="password" required placeholder="Password" id="registerPass">
        <input type="password" required placeholder="Confirm Password" id="confirmPass">
        <button type="submit" id="registerBtn">Register</button>
    </form>
    `;
}

export function initRegister() {
    const registerContainer = document.getElementById("register-container")
    const name = document.getElementById('registerName');
    const email = document.getElementById('registerEmail');
    const password = document.getElementById('registerPass');
    const confirmPassword = document.getElementById('confirmPass');
    const registerBtn = document.getElementById('registerBtn')

    registerBtn.addEventListener('click', async (e) => {
        e.preventDefault()
        if(!registerContainer.checkValidity()){
            alert("Enter Credentials")
            return
        }
        if(password.value != confirmPassword.value){
            alert("Password mismatch!")
            return
        }
        try{
            const res = await fetch(`${API_URL}/register`, {
            method: 'POST',
            headers: {
                "Content-Type" : "application/json"
            },
            body: JSON.stringify({
                email: email.value,
                password : password.value,
                full_name : name.value
            })
            });
            const data = await res.json();
            if (res.ok) {
                if(data != null){
                    throw{
                        message : data.detail
                    }
                }else{
                    navigate("/login")
                }
            }
        }catch(message){
            alert(message.message)
        }
    });
    }
