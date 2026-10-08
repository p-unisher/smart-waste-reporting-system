// Register form

document.getElementById("registerForm").addEventListener("submit", function(event) {

    event.preventDefault();

    let name = document.getElementById("name").value;
    let email = document.getElementById("email").value;
    let phone = document.getElementById("phone").value;
    let password = document.getElementById("password").value;


    if (name == "" || email == "" || phone == "" || password == "") {

        alert("Please fill all the details.");

    } else {

        alert("Registration button is working.");

        // Registration will be connected
        // with Flask and SQLite later.

    }

});