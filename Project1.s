	.data
C:			.word	0:100					#array size 100 	int a[] = $a0	int low = $a1	int high = $a2
Space: 		.asciiz " "
MyArray: 	.word 	1, 4, 7, 10, 25, 3, 5, 13, 17, 21
MyNewArray: .word 	56, 3, 46, 47, 34, 12, 1, 5, 10, 8, 33, 25, 29, 31, 50, 43
pre:		.asciiz "\nList of unsorted merge arrays: "
post:		.asciiz "\nList of sorted arrays: "
msPrompt: 	.asciiz "\nList of unsorted mergesort array: "
	.text
main:		#Prints unsorted array


			la 		$a0, msPrompt		
			li		$v0, 4					
			syscall							#Prints prompt

			la 		$a0, MyNewArray			#$a0 = MyArray
			addi 	$a1, $zero, 16			#$a1 = 10
			jal		printcode
			la 		$a0, MyNewArray			#loads array
			add 	$a1, $zero, $zero
			addi 	$a2, $zero, 15
			jal 	mergesort 					#runs merge

			la 		$a0, post
			li 		$v0, 4
			syscall

			la 		$a0, MyNewArray
			addi 	$a1, $zero, 16
			jal		printcode
			


			la 		$a0, pre 				#Prints Merge			
			li		$v0, 4					
			syscall							#Prints prompt

			la 		$a0, MyArray			#$a0 = MyArray
			addi 	$a1, $zero, 10			#$a1 = 10
			jal		printcode
			la 		$a0, MyArray			#loads array
			add 	$a1, $zero, $zero
			addi 	$a2, $zero, 9
			addi 	$a3, $zero, 4
			jal 	merge 					#runs merge

			la 		$a0, post				#runs post prompt
			li		$v0, 4
			syscall

			la 		$a0, MyArray
			addi 	$a1, $zero, 10
			jal		printcode
			li 		$v0, 10
			syscall




mergesort:	addi 	$sp, $sp, -16			#stack size for low, mid, hi, return address	
			sw 		$a1, 4($sp)				#stores low into stack
			sw 		$a2, 8($sp)				#stores high into stack
			sw 		$ra, 12($sp)			#stores original return address into stack
			slt 	$t1, $a1, $a2
			beq 	$t1, $zero, MSExit		#When the for loop is false, goes to Exit
			add 	$t2, $a1, $a2			#low + high = $t2
			addi 	$t3, $zero, 2			#assigns 2 to $t3
			div 	$t2, $t3				#(low+high)/2
			mflo 	$s0						#mid = (low+high)/2
			sw 		$s0, 0($sp)				#stores mid into stack
			add 	$a2, $zero, $s0			#Third argument = mid
			#begin mergesort(a,low,mid)	
			jal 	mergesort				
			lw 		$s0, 0($sp)				#Loads mid, so it won't take the wrong mid
			addi    $a1, $s0, 1				#Mid + 1
			lw      $a2, 8($sp)				#Retrieves high from saved word
			#begin mergesort(a, mid+1, high)
			jal	 	mergesort	
			lw 		$a2, 8($sp)				#$a2 = high (reloaded)
			lw 		$a3, 0($sp)				#$a3 = Mid 	(reloaded)
			lw		$a1, 4($sp)				#Reloads second argument = low
			jal		merge                 	#merge(a,low,high,mid)

MSExit:		lw 		$ra, 12($sp)			#Returns to original return address
			addi	$sp, $sp, 16			#Frees Space
			jr 		$ra

			#int a[] = $a0, int low = $a1, int high = $a2, int mid = $a3
merge:		add 	$t0, $zero, $a1			#int i = low
			add 	$t8, $zero, $a1			#int i = low
			add 	$t1, $zero, $a1			#int k = low
			addi 	$t2, $a3, 1				#int j = mid + 1
			addi	$t5, $zero, 4			#$t5 = 4
			addi 	$t3, $a3, 1				#mid+1 to prepare for i <= mid
			addi 	$t4, $a2, 1				#same as above for j <= high
			la      $s7, C					#Loads Array C

while:		slt 	$t7, $t0, $t3			#(i <= mid)
			slt 	$t6, $t2, $t4			#(j <= high)
			and		$t7, $t7, $t6			#(i <= mid && j <= high)
			beq		$t7, $zero, while2		
			#if(a[i]< a[j])
			mult 	$t5, $t0				#4 * i
			mflo	$s2						#$s2 = i * 4
			add 	$s4, $a0, $s2			#$s4 = a[i]
			lw		$s5, 0($s4)				#$s5 = a[i]
			mult 	$t5, $t2				#4 * j
			mflo 	$s3						#$s3 = 4*j
			add 	$s3, $a0, $s3			#s3 takes j offset of the array
			lw 		$s2, 0($s3)				#$s2 = a[j]
			mult	$t5, $t1				#4 * k
			mflo	$t7						#$t7 = k * 4
			add    	$s6, $s7, $t7			#new $s6 = c[k]
			slt 	$t6, $s5, $s2			#a[i]<a[j]
			beq 	$t6, $zero, else		#$t6 = a[i]<a[j]
			#Start of c[k] = a[i]
			sw 		$s5, 0($s6)				#c[k] = a[i]
			addi	$t1, $t1, 1				#k++
			addi 	$t0, $t0, 1				#i++
			j 		while

			# start if statement, need to call a new c[k]
else:		sw 		$s2, 0($s6)				#c[k] = a[j]
			addi	$t1, $t1, 1				#k++
			addi 	$t2, $t2, 1				#j++
			j 		while
			#int a[] = $a0, int low = $a1, int high = $a2, int mid = $a3, i = $t0, j = $t2, k = $t1

while2:		slt 	$t9, $t0, $t3			#(i <= mid)
			beq 	$t9, $zero, while3		#if mid !<= 1
			mult 	$t5, $t0				#4 * i
			mflo	$s2						#$s2 = i * 4
			add 	$s2, $a0, $s2			#$s4 = a[i]
			lw		$s5, 0($s2)				#$s5 = $s2
			mult	$t5, $t1				#4 * k
			mflo	$t7						#$t7 = k * 4
			add    	$s6, $s7, $t7			#new $s6 = c[k]
			sw 		$s5, 0($s6)				#c[k] = a[i]
			addi	$t1, $t1, 1				#k++
			addi 	$t0, $t0, 1				#i++
			j 		while2

while3: 	slt 	$t6, $t2, $t4			#(j <= high)
			beq 	$t6, $zero, for			#if mid !<= 1
			mult	$t5, $t1				#4 * k
			mflo	$t7						#$t7 = k * 4
			add    	$s6, $s7, $t7			#new $s6 = c[k]
			mult 	$t5, $t2				#4 * j
			mflo 	$s3						#$s3 = 4*j
			add 	$s3, $a0, $s3			#s3 takes j offset of the array
			lw 		$s2, 0($s3)				#$s2 = a[j]
			sw 		$s2, 0($s6)				#c[k] = a[j]
			addi	$t1, $t1, 1				#k++
			addi 	$t2, $t2, 1				#j++
			j 		while3

for: 		slt 	$t6, $t8, $t1 			#i<k
			beq 	$t6, $zero, MergeExit
			mult 	$t5, $t8				#4 * i
			mflo	$s2						#$s2 = i * 4
			add    	$s6, $s7, $s2			#new $s6 = c[i]
			lw 		$s5, 0($s6)				#c[i] = a[i]
			add 	$s4, $a0, $s2			#$s4 = a[i]
			sw		$s5, 0($s4)				#$s5 = a[i]
			#int a[] = $a0, int low = $a1, int high = $a2, int mid = $a3, i = $t0, j = $t2, k = $t1
			addi 	$t8, $t8, 1 			# i++
			j 		for

MergeExit: 	jr 		$ra




#PrintArray: .data
#Prompt:		.asciiz "\nPlease insert your array\n"
#Space: 		.asciiz " "

#			.text
#MainPA: 	la $a0, Prompt				
#			li $
printcode:
			move 	$s0, $a0       			#Set array
			add 	$t1, $zero, $zero   	#$t1 = 0
			addi 	$t4, $zero, 1  			#$t4 = 1

forLoop:
			bgt 	$t4, $a1, quit  		#quits if $s0 > $a1
			addi 	$t0, $zero, 1    		#$t0 = 1
			move 	$v0, $t0        		#$v0 for syscall
			add 	$s2, $t1, $s0    		#$s2 = 0($s0=$a0)
			lw 		$s3, 0($s2)       		#$s3 holds $s2
			move 	$a0, $s3        		#$a0 holds $s3
			syscall           				
			la 		$s7, Space     			#prints space
			move 	$a0, $s7     			#Space = $a0
			addi 	$v0, $v0, 3      		#adds 3 to v0 to equal 4.
			syscall
			addi 	$t1, $t1, 4      		#increments offset by 4
			addi 	$t4, $t4, 1      		#increment the stopping factor 1
			j 		forLoop

quit:		jr 		$ra