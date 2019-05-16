<?php
   include("config.php");
   session_start();
   
   if($_SERVER["REQUEST_METHOD"] == "POST") {
      // username and password sent from form 
      if($_SERVER["REQUEST_METHOD"] == "POST") {
				// username and password sent from form 
				
				$CT_id = mysqli_real_escape_string($db,$_POST['username']);
				$password = mysqli_real_escape_string($db,$_POST['password']); 
				$sql = "SELECT id FROM ct WHERE username = '$CT_id' and passcode = '$password'";
      $result = mysqli_query($db,$sql);
      $row = mysqli_fetch_array($result,MYSQLI_ASSOC);
      $active = $row['active'];
      
      $count = mysqli_num_rows($result);




<!DOCTYPE html>
<html>
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<script src="https://use.fontawesome.com/d1341f9b7a.js"></script>
	<script src="https://ajax.googleapis.com/ajax/libs/angularjs/1.6.9/angular.min.js"></script>
	<link rel="stylesheet" href="css1.css">
		<link rel="stylesheet"href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css">
	<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
	<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js"></script>
	<title>Care-taker Login</title>
</head>
<script>
$(document).ready(function(){
 $(".btn2").dblclick(function(){
  	window.location.href="patientpage.html";
  });
});

</script>
<style>
 body{
 	background-image: url("bg6.jpg");
 }
 
 
</style>
<body>
	<div class="container-fluid">
   <h1 align="center"><b>Care-taker Login</b></h1>
<div class="centered" ng-app="careTakerApp">
	<table>

	<img src="nurse.png" alt="" class="box-img" align="center"><br><br>
	<tr>
		<td><span class="glyphicon glyphicon-user"></span>
		<b>CareTaker Name</b></td>
		<td>
	<input class="text-primary"id="usn" type="text" placeholder="CT_id" ng-model="cusr"></td></tr>
	<tr><td><br></td><td><br></td></tr>
	<tr>
		<td><span class="glyphicon glyphicon-lock"></span><b>Password</b></td>
	<td><input class="text-primary"id="pwd" type="Password" placeholder="Password" ng-model="cpwd"></td></tr>
	<tr><td><br></td><td><br></td></tr>
	<tr>
		<td>
			<button id="btn1" type="button" class="btn btn-primary" onclick="cleart();">Clear</button>
	    </td>
	<td><button id="btn2" type="submit" class="btn btn-success" align="center"><a href="patientpage.html"></a>Login</button></td></tr>
</table>
</div>
</div>
</form>
<script type="text/javascript">
	 
  function cleart(){
  	document.getElementById('usn').value="";
    document.getElementById('pwd').value="";
}
</script>
</body>
</html>