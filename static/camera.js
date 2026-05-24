const video = document.getElementById("video");

navigator.mediaDevices.getUserMedia({
    video:true
})
.then(stream=>{
    video.srcObject=stream;
});

function authenticateUser(){

    const canvas=document.getElementById("canvas");

    const ctx=canvas.getContext("2d");

    canvas.width=video.videoWidth;
    canvas.height=video.videoHeight;

    ctx.drawImage(video,0,0);

    const image=canvas.toDataURL("image/jpeg");

    fetch("/authenticate",{

        method:"POST",

        headers:{
            "Content-Type":"application/json"
        },

        body:JSON.stringify({
            image:image
        })

    })

    .then(res=>res.json())

    .then(data=>{

        document.getElementById("result").innerHTML=
        data.message;

    });

}