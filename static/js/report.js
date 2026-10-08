// Waste report form

document.getElementById("reportForm").addEventListener("submit", function(event) {

    event.preventDefault();

    let wasteType = document.getElementById("wasteType").value;
    let location = document.getElementById("location").value;
    let description = document.getElementById("description").value;
    let photo = document.getElementById("wastePhoto").value;


    if (wasteType == "" || location == "" || description == "") {

        alert("Please fill all the required details.");

    } else {

        alert("Waste report submitted successfully.");

        // Later this data will be
        // sent to Flask backend.

    }

});